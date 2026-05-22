import pathlib
import shutil
import zipfile


def main():
    cwd = pathlib.Path.cwd()

    assets = cwd.joinpath("assets").resolve(strict=True)
    dist = cwd.joinpath("dist").resolve(strict=True)

    zip = dist / "trust-generator.zip"
    print(f"{zip!s}")

    for doc in assets.rglob('*.docx'):
        if (out := dist / doc.name).exists():
            out.unlink()
        shutil.copy2(doc, out)

    with zipfile.ZipFile(zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in dist.iterdir():
            if f.suffix == ".zip":
                continue
            zf.write(f, f.name)
            print(f"    - {f.name} ({f.stat().st_size} bytes)")

    for doc in dist.rglob("*.docx"):
        doc.unlink()

if __name__ == "__main__":
    main()