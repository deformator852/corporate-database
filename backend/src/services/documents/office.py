import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from exceptions import AppError

CONVERT_TIMEOUT_SECONDS = 60


async def convert_doc_to_docx(content: bytes) -> bytes:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise AppError(
            "unavailable",
            "Could not convert the Word document.",
            status_code=503,
        )

    with tempfile.TemporaryDirectory(prefix="doc-convert-") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "source.doc"
        outdir = tmp_path / "out"
        profile = tmp_path / "lo-profile"
        outdir.mkdir()
        profile.mkdir()
        await asyncio.to_thread(source.write_bytes, content)

        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        process = await asyncio.create_subprocess_exec(
            soffice,
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--norestore",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to",
            "docx",
            "--outdir",
            str(outdir),
            str(source),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            await asyncio.wait_for(
                process.communicate(),
                timeout=CONVERT_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise AppError(
                "unavailable",
                "Could not convert the Word document.",
                status_code=503,
            ) from exc

        if process.returncode != 0:
            raise AppError(
                "invalid",
                "Could not convert the Word document.",
                status_code=400,
            )

        produced = _converted_docx(outdir)
        return await asyncio.to_thread(produced.read_bytes)


def _converted_docx(outdir: Path) -> Path:
    produced = outdir / "source.docx"
    if produced.is_file():
        return produced
    matches = [path for path in outdir.glob("*.docx") if path.is_file()]
    if len(matches) != 1:
        raise AppError(
            "invalid",
            "Could not convert the Word document.",
            status_code=400,
        )
    return matches[0]
