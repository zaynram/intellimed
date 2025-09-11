from src import arguments, analyze, extract

if __name__ == "__main__":
    args = arguments.parse()
    match args.command:
        case "analyze":
            analyze.analyze_text(*args.params())
        case "extract":
            extract.plaintext_from_pdfs(*args.params())
        case _:
            arguments.help()
