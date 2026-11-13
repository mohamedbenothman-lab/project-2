@echo off
rem Run from Project_3\ : compares variants without examples on both hold-outs.
set JUDGE_EXAMPLES=0
cd /d %~dp0..
for %%V in (C A) do (
  set JUDGE_VARIANT=%%V
  call :one %%V
)
cd starter_pack
echo ===== OR(C,A) criterion1
python ..\tools\combine.py or ho1_C.csv ho1_A.csv ho1_OR.csv
python score.py ho1_OR.csv ho1.jsonl --baseline baseline_dev_verdicts.csv | findstr /C:"COMBINED" /C:"original pass"
echo ===== OR(C,A) criterion2
python ..\tools\combine.py or ho2_C.csv ho2_A.csv ho2_OR.csv
python score.py ho2_OR.csv ho2.jsonl --baseline ho2_base.csv | findstr /C:"COMBINED" /C:"original pass"
cd ..
goto :eof
:one
echo ===== %1 criterion2
python tools\run.py eval2 | findstr /C:"delta" /C:"original pass"
copy /y starter_pack\ho2.csv starter_pack\ho2_%1.csv >nul
echo ===== %1 criterion1
python tools\run.py eval1 | findstr /C:"delta" /C:"original pass"
copy /y starter_pack\ho1.csv starter_pack\ho1_%1.csv >nul
goto :eof
