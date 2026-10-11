import asyncio
import os
import shutil
import signal
import tempfile
from pathlib import Path

from exceptions import AppError

CONVERT_TIMEOUT_SECONDS = 60
# Each conversion starts a LibreOffice of a few hundred MB: a burst of .doc
# uploads must not take all the memory of the backend.
_CONVERSIONS = asyncio.Semaphore(2)
# LibreOffice parses files from users: it gets no secrets of the backend
# (keys, passwords), only what it needs to run.
_PASSED_ENV = ("PATH", "LANG", "LC_ALL", "TMPDIR")


async def convert_doc_to_docx(content: bytes) -> bytes:
    async with _CONVERSIONS:
        return await _convert(content)


async def _convert(content: bytes) -> bytes:
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

        env = {name: os.environ[name] for name in _PASSED_ENV if name in os.environ}
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
            # Its own process group: soffice starts soffice.bin, which a kill
            # of soffice alone would leave running.
            start_new_session=True,
        )
        try:
            await asyncio.wait_for(
                process.communicate(),
                timeout=CONVERT_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
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
