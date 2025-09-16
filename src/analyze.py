from __future__ import annotations
from .extract import Extractor
from .utils import DATA_DIR, console, retry, timings, dumplocals
import datetime as dt
import math
import json
import ollama
import typing

if typing.TYPE_CHECKING:
    from .typeshed import *

from pathlib import Path

SYSTEM_PROMPT = typing.final("""
You are a medical data analyst tasked with extracting information from the plaintext parsed from a set of PDF files containing an individual's medical records.

Instructions:
1. Review the following description of the accident, date of the accident, and medical record plaintext.
2. Identify a list of all of the individual's diagnosed injuries and a list of all of their treatments, including medications and physical therapy sessions, that are a direct result of this specific accident.
3. Only include information directly relevant to this specific accident. Do not include any other medical history.
4. If no related injuries or treatments are found, return empty arrays.
5. Do not include any text, notes, or explanations outside of the JSON object.
6. Disregard any gibberish and textual artifacting leftover from PDF file parsing.
""")

PROMPT_TEMPLATE = typing.final("""
Use the following information to extract the relevant 'injuries' and 'treatments'.

Accident Description:
{desc}

Accident Date:
{date}

Medical Record Text:
{plaintext}
""")


RESPONSE_SCHEMA = typing.final({
    "type": "object",
    "properties": {
        "injuries": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "treatments": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
    },
})

PROMPT_LENGTH = typing.final(
    len(SYSTEM_PROMPT) + len(PROMPT_TEMPLATE.format(desc="", date="", plaintext=""))
)

TODAY = dt.datetime.now().date().isoformat()


class Analyzer(Extractor):
    max_tokens: int = 16000
    temperature: float = 0.2

    model_id: str = "gemma3n:e4b"

    @property
    def _options(self) -> ollama.Options:
        return ollama.Options(
            temperature=self.temperature,
            num_ctx=self.max_tokens,
            num_predict=4096,
            use_mlock=True,
            low_vram=True,
        )

    debug: bool = False

    desc: str
    date: date

    @retry(max_retries=3)
    def _pull_model(self) -> None:
        models = {m.model for m in ollama.list().models}
        if self.model_id not in models:
            ollama.pull(self.model_id)

    @property
    def config(self) -> JSONDict:
        input_files: JSONList = [f.name for f in self.path.iterdir() if f.suffix == ".pdf"]
        return {
            "model_id": self.model_id,
            "input_files": input_files,
            "output_directory": self.results_dir.as_uri(),
            "accident_info": {
                "date": self.date.isoformat(),
                "description": self.desc,
            },
        }

    @dumplocals
    def analyze(self) -> None:
        """
        Analyzes all text files in a directory using a local Gemma:3n model
        to extract injury and treatment information.

        Args:
            description (str): A description of the accident for context.
            date (date): The date of the accident.
            directory_path (Path): The path to the directory with extracted text files.
        """

        from .utils import track

        self._pull_model()

        text_files = self._extract_text()

        if not text_files:
            console.error(
                "Could not find any valid plaintext files.",
                exception=FileNotFoundError,
            )

        output_text: str = ""
        match_counts: dict[str, Any] = {}

        console.json(global_configuration=self.config)

        for f in track(
            iterable=text_files,
            desc="analyzing medical records",
        ):
            plaintext = f.read_text(encoding="utf-8")

            prompt = PROMPT_TEMPLATE.format(
                desc=self.desc,
                date=self.date,
                plaintext=plaintext,
            )

            text_length: int = len(plaintext)
            total_chars: int = text_length + PROMPT_LENGTH

            if math.ceil(total_chars / 4) > self.max_tokens:
                console.error(
                    f"Skipping analysis for {f.name}.",
                    f"Text length ({text_length}) exceeded maximum allowed (max_tokens: {self.max_tokens}).",
                )
                continue

            console.json("current_file_info", text_length=text_length, prompt=prompt)

            try:

                @timings()
                def generate_response() -> str:
                    response = ollama.generate(
                        model=self.model_id,
                        system=SYSTEM_PROMPT,
                        format=RESPONSE_SCHEMA,
                        prompt=prompt,
                        options=self._options,
                        # keep alive for 1 hour
                        keep_alive=3600,
                    )

                    return response.response

                output_text = generate_response()
                analysis_data: AnalysisResults = json.loads(output_text)

                from .validate import ValidationDict

                results, match_counts[f.stem] = ValidationDict(
                    plaintext, analysis_data
                ).validate()

                out_file = self.results_dir / f"{f.stem}_analysis.json"
                out_file.write_text(json.dumps(results, indent=4))

            except json.JSONDecodeError as e:
                console.error(f"Error parsing JSON from LLM for {f.name}.", exception=e)
                raise e

            except Exception as e:
                console.error(exception=e)
                raise e

        console.json(match_counts=match_counts)

    @staticmethod
    def init_analysis_args(subparsers: Subparsers) -> None:
        from .utils import argtype

        parser = subparsers.add_parser(
            "analyze",
            description="Analyze medical record PDF files using local LLM inferencing.",
            prog="Analyze Files",
        )
        options = parser.add_argument_group("Options")
        options.add_argument(
            "--path",
            metavar="Folder",
            required=True,
            help="The folder containing the medical records. Only PDF files will be used for analysis.",
            widget="DirChooser",
            gooey_options={"default_path": DATA_DIR},
            type=Path,
        )
        accident_details = options.add_argument_group(
            "Accident Details",
            description="Provide additional information to better ground analysis.",
        )
        accident_details.add_argument(
            "--desc",
            metavar="Description",
            required=True,
            help="A brief description of the related accident.",
            widget="Textarea",
            gooey_options={"initial_value": ""},
            type=str,
        )
        accident_details.add_argument(
            "--date",
            metavar="Date",
            help="The date that the accident occured on.",
            widget="DateChooser",
            default=TODAY,
            type=argtype.datestring,
        )
        config = parser.add_argument_group("Configuration")
        custom_folders = config.add_argument_group(
            "Custom Folders",
            description="Configure the location(s) of output files.",
        )
        custom_folders.add_argument(
            "--custom_text_dir",
            metavar="Plaintext Folder",
            help="The folder to save extracted plaintext to.",
            widget="DirChooser",
            gooey_options={"default_path": DATA_DIR},
            type=Path,
        )
        custom_folders.add_argument(
            "--custom_results_dir",
            metavar="Results Folder",
            help="The folder to save analysis results to.",
            widget="DirChooser",
            gooey_options={"default_path": DATA_DIR},
            type=Path,
        )
        dev = parser.add_argument_group("Developer")
        dev.add_argument(
            "--debug",
            metavar="Debug",
            choices=[True, False],
            default=False,
            help="If set to True, will print the program configuration and exit without execution.",
            type=argtype.boolstring,
        )
        llm_params = dev.add_argument_group(
            "LLM Parameters",
            description="Configure relevant parameters for the LLM. "
            "Do not change unless you know what you're doing.",
        )
        llm_params.add_argument(
            "--max_tokens",
            metavar="Max Tokens",
            help="The maximum amount of tokens for a single request.",
            widget="IntegerField",
            gooey_options={
                "min": 8000,
                "max": 64000,
                "increment": 8000,
            },
            default=16000,
            type=int,
        )
        llm_params.add_argument(
            "--model_id",
            metavar="Model Id",
            help="The identifier for the model to use for analysis.",
            gooey_options={"initial_value": "gemma3n:e4b"},
            type=argtype.nowhitespaces,
        )
