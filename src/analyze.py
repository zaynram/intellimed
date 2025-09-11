# medical_record_analyzer.py

import json
import ollama
import datetime
import pathlib
import tqdm
import typing

MAX_TEXT_TOKENS_REAL: int = 120000
MAX_TEXT_TOKENS_EST: int = 96000
OLLAMA_MODEL: str = "gemma3n:e4b"
PRETRAINED_ID: str = "google/gemma-3n-E4B-it"

config_json_template = """
analysis_configuration = {
    "cwd": "{cwd}",
    "ollama_model": "{model}",
    "accident_info": {
        "date": {date},
        "description": "{desc}"
    }
}
"""


def analyze_text(
    description: str,
    date: datetime.date,
    directory_path: pathlib.Path,
) -> None:
    """
    Analyzes all text files in a directory using a local Gemma:3n model
    to extract injury and treatment information.

    Args:
        description (str): A description of the accident for context.
        date (date): The date of the accident.
        directory_path (Path): The path to the directory with extracted text files.
    """

    print(
        config_json_template.format(
            cwd=directory_path,
            model=OLLAMA_MODEL,
            date=date,
            desc=description,
        )
    )

    try:
        ollama.pull(OLLAMA_MODEL)  # Ensures the model is available
    except Exception as e:
        return print(
            f"Error connecting to Ollama or pulling model: {e}",
            "Please ensure the Ollama server is running and the model exists locally.",
            sep="\n",
        )

    output_dir = directory_path / "analysis_results"
    output_dir.mkdir(exist_ok=True)

    output_text: str = ""
    analysis_data: dict[str, typing.Any] = {}
    for f in tqdm.tqdm(
        iterable=directory_path.iterdir(),
        desc="analyzing medical records",
        unit="file",
        colour="cyan",
    ):
        if f.name.lower().endswith(".txt"):
            plaintext = (directory_path / f.name).read_text(encoding="utf-8")

            appx_token_ct = int(len(plaintext) / 4)

            if appx_token_ct > MAX_TEXT_TOKENS_EST:
                from transformers import AutoTokenizer

                tokenizer = AutoTokenizer.from_pretrained(PRETRAINED_ID)
                real_token_ct = len(tokenizer.encode(plaintext))
                excess_token_ct = MAX_TEXT_TOKENS_REAL - real_token_ct

                if excess_token_ct > 0:
                    raise ValueError("ExcessTokenCount: " + str(excess_token_ct))

            # Construct a structured prompt for the LLM
            prompt = f"""
            You are a medical data analyst tasked with extracting information from a medical record.

            Instructions:
            1.  Review the following medical record text.
            2.  The patient was involved in an accident described as '{description}' on the date '{date}'.
            3.  Identify all diagnosed injuries and a list of all treatments, medications, and physical therapy sessions that are a direct result of this specific accident.
            4.  Present the information in a JSON format with two top-level keys: "injuries" (an array of strings) and "treatments" (an array of strings).
            5.  Only include information directly relevant to this specific accident. Do not include any other medical history.
            6.  If no related injuries or treatments are found, return empty arrays.
            7.  Do not include any text, notes, or explanations outside of the JSON object.

            Medical Record Text:
            {plaintext}
            """

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

                out_file = output_dir / f"{f.stem}_analysis.json"

                fmt_output = json.dumps(analysis_data, indent=4)
                out_file.write_text(fmt_output)

                print(fmt_output)

            except json.JSONDecodeError as e:
                print(f"Error parsing JSON from LLM for {f.name}: {e}")
                print("LLM output was:\n", output_text)
            except Exception as e:
                print(f"An error occurred during analysis of {f.name}: {e}")
