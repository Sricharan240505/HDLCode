"""
judge.py — compiles a user's Verilog module against a hidden testbench using
Icarus Verilog (iverilog + vvp), inside a temp directory, with a wall-clock
timeout so infinite loops can't hang the app.
"""
import subprocess
import tempfile
import os
import re
import shutil
IVERILOG = os.getenv(
    "IVERILOG_PATH",
    shutil.which("iverilog") or r"D:\iverilog\bin\iverilog.exe"
)

VVP = os.getenv(
    "VVP_PATH",
    shutil.which("vvp") or r"D:\iverilog\bin\vvp.exe"
)
TIMEOUT_SECONDS = 10


def run_submission(user_code: str, testbench_code: str) -> dict:
    """
    Returns a dict:
      {
        "status": "PASS" | "FAIL" | "COMPILE_ERROR" | "TIMEOUT" | "ERROR",
        "message": str,          # human-readable summary
        "raw_output": str,       # full simulator stdout/stderr
      }
    """
    workdir = tempfile.mkdtemp(prefix="hdlcode_")
    try:
        sol_path = os.path.join(workdir, "submission.v")
        tb_path = os.path.join(workdir, "testbench.v")
        sim_path = os.path.join(workdir, "sim.out")

        with open(sol_path, "w") as f:
            f.write(user_code)
        with open(tb_path, "w") as f:
            f.write(testbench_code)

        # --- Compile ---
        compile_proc = subprocess.run(
            [IVERILOG, "-g2012", "-o", sim_path, sol_path, tb_path],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        if compile_proc.returncode != 0:
            return {
                "status": "COMPILE_ERROR",
                "message": "Compilation failed.",
                "raw_output": compile_proc.stderr or compile_proc.stdout,
            }

        # --- Simulate ---
        try:
            sim_proc = subprocess.run(
                [VVP, sim_path],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "message": f"Simulation exceeded {TIMEOUT_SECONDS}s (likely an infinite loop or missing $finish).",
                "raw_output": "",
            }

        output = sim_proc.stdout + sim_proc.stderr

        if re.search(r"RESULT:PASS", output):
            return {"status": "PASS", "message": "All hidden tests passed.", "raw_output": output}
        elif re.search(r"RESULT:FAIL", output):
            return {"status": "FAIL", "message": "Some hidden tests failed.", "raw_output": output}
        else:
            return {
                "status": "ERROR",
                "message": "Simulation ran but produced no RESULT marker — check for a missing $finish.",
                "raw_output": output,
            }

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "message": "Compilation timed out.", "raw_output": ""}
    except Exception as e:
        return {"status": "ERROR", "message": f"Judge internal error: {e}", "raw_output": str(e)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def check_tools_available() -> bool:
    return os.path.exists(IVERILOG) and os.path.exists(VVP)
