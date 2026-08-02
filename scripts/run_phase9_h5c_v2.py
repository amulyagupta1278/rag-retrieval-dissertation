#!/usr/bin/env python3
"""Run frozen H5c-v2 through shared zero-retry executor."""
from pathlib import Path
import run_phase9_h5c as runner
ROOT=Path(__file__).resolve().parents[1]
runner.FR=ROOT/'runs/phase9_h5c_v2/freeze'
runner.OUT=ROOT/'runs/phase9_h5c_v2/generation'
runner.APPROVAL=ROOT/'audits/phase9_h5c_v2/cost_approval.json'
if __name__=='__main__': raise SystemExit(runner.main())
