from __future__ import annotations

import math
import json
import ollama
import typing


from .extract import Extractor

if typing.TYPE_CHECKING:
    from .types import *


prompt_template = """
You are a medical data analyst tasked with extracting information from a medical record.

Instructions:
1.  Review the following medical record text(s).
2.  The patient was involved in an accident described as '{desc}' on the date '{date}'.
3.  Identify all diagnosed injuries and a list of all treatments, medications, and physical therapy sessions that are a direct result of this specific accident.
4.  Present the information in a JSON format with two top-level keys: "injuries" (an array of strings) and "treatments" (an array of strings).
5.  Only include information directly relevant to this specific accident. Do not include any other medical history.
6.  If no related injuries or treatments are found, return empty arrays.
7.  Do not include any text, notes, or explanations outside of the JSON object.

Medical Record Text:
{plaintext}
"""


def compute_prompt_length() -> int:
    return len(prompt_template.format(desc="", date="", plaintext=""))


class Analyzer(Extractor):
    max_tokens_per_request: int = 96000
    ollama_model_id: str = "gemma3n:e4b"

    desc: str
    date: date

    def _prepare_analysis(self) -> Iter[Path]:
        text_files = self._extract_text()

        config: JSONDict = {
            "analysis_configuration": {
                "ollama_model": self.ollama_model_id,
                "paths": {
                    "results": self.results_dir.as_uri(),
                    "plaintext": self.text_dir.as_uri(),
                },
                "details": {
                    "date": self.date.isoformat(),
                    "description": self.desc,
                },
            }
        }

        print(json.dumps(obj=config, indent=4), flush=True)

        try:
            ollama.pull(self.ollama_model_id)
        except Exception as e:
            from .utils import error

            error(
                "Error connecting to Ollama or pulling model.",
                "Please ensure the Ollama server is running and the model exists locally.",
                exception=e,
            )

        return text_files

    def analyze(self) -> None:
        """
        Analyzes all text files in a directory using a local Gemma:3n model
        to extract injury and treatment information.

        Args:
            description (str): A description of the accident for context.
            date (date): The date of the accident.
            directory_path (Path): The path to the directory with extracted text files.
        """

        from .utils import track, error, log

        text_files = self._prepare_analysis()

        if not text_files:
            error(
                "Could not find any valid plaintext files.",
                exception=FileNotFoundError,
            )

        output_text: str = ""
        analysis_data: dict[str, typing.Any]
        summaries: dict[str, Any] = {}

        for f in track(
            iterable=text_files,
            desc="analyzing medical records",
        ):
            plaintext = f.read_text(encoding="utf-8")

            # Construct a structured prompt for the LLM
            prompt = prompt_template.format(
                desc=self.desc,
                date=self.date,
                plaintext=plaintext,
            )

            text_length = self._metadata[f.stem].get("character_count", len(plaintext))
            total_chars: int = text_length + compute_prompt_length()

            if math.ceil(total_chars / 4) > self.max_tokens_per_request:
                raise NotImplementedError

            try:
                response = ollama.chat(
                    model="gemma:3n",
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1},
                )

                output_text = response["message"]["content"]

                # The LLM may add markdown formatting, so we need to strip it
                if output_text.startswith("```json") and output_text.endswith("```"):
                    output_text = output_text[7:-3].strip()

                analysis_data = json.loads(output_text)

                from .validate import ValidationDict

                results, summaries[f.stem] = ValidationDict(
                    plaintext,
                    analysis_data,
                ).validate()

                out_file = self.results_dir / f"{f.stem}_analysis.json"
                out_file.write_text(json.dumps(results, indent=4))

            except json.JSONDecodeError as e:
                error(
                    f"Error parsing JSON from LLM for {f.name}.",
                    f"Output Text:\n{output_text}",
                    exception=e,
                )

            except Exception as e:
                error(f"An error occurred during analysis of {f.name}", exception=e)

        log(json.dumps(summaries, indent=4))
