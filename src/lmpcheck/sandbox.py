from pathlib import Path
from .models import Finding


def run_sandbox(script: Path, lmp_binary: str = "lmp", timeout: int = 60) -> list[Finding]:
    import shutil
    if not shutil.which(lmp_binary):
        return [Finding(
            severity="warning",
            category="sandbox_skipped",
            file=script,
            line=0,
            message=f"lmp binary `{lmp_binary}` not found in PATH; skipping sandbox stage",
            suggestion="Install LAMMPS locally or use --lmp-binary to specify the path, or --no-sandbox to suppress this warning",
        )]
    return []
