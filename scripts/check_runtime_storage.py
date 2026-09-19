"""Block replacement when unmounted runtime files exist. Never migrate storage."""

import json
import subprocess
import tarfile


def covered(path, mounts):
    return any(path == m["Destination"] or path.startswith(m["Destination"].rstrip("/") + "/")
               for m in mounts if m["Type"] in {"bind", "volume"})


def main():
    for service in ("backend", "worker"):
        ids = subprocess.check_output(
            ["docker", "compose", "--profile", "background", "ps", "--all", "--quiet", service],
            text=True,
        ).split()
        for container in ids:
            meta = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
            for directory in ("/app/uploads", "/app/vector_db"):
                if covered(directory, meta["Mounts"]):
                    continue
                # Read a tar stream for running or stopped containers, without loading file bodies.
                with subprocess.Popen(["docker", "cp", f"{container}:{directory}/.", "-"],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
                    try:
                        with tarfile.open(fileobj=proc.stdout, mode="r|*") as archive:
                            for member in archive:
                                if member.isfile() or member.issym() or member.islnk():
                                    raise RuntimeError("Unmounted runtime files; storage migration required")
                    except Exception:
                        proc.kill()
                        raise
                    finally:
                        proc.stdout.close()
                    if proc.wait():
                        raise RuntimeError("Cannot verify runtime directory; replacement blocked")
    print("Runtime storage preflight passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- redact Docker output at the CLI boundary.
        print(f"ERROR runtime storage preflight failed ({type(exc).__name__}); deployment blocked")
        raise SystemExit(1) from None
