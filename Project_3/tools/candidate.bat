@echo off
rem Run from Project_3\ after compare.bat (needs ho*_C.csv and ho*_A.csv). Does NOT touch final_judge.py.
setlocal
cd /d %~dp0..
set JUDGE_FILE=candidate_judge.py
echo ===== D criterion2
python tools\run.py eval2 | findstr /C:"delta" /C:"original pass"
copy /y starter_pack\ho2.csv starter_pack\ho2_D.csv >nul
echo ===== D criterion1
python tools\run.py eval1 | findstr /C:"delta" /C:"original pass"
copy /y starter_pack\ho1.csv starter_pack\ho1_D.csv >nul
cd starter_pack
for %%M in (or and) do (
  echo ===== %%M[C,D] criterion1
  python ..\tools\combine.py %%M ho1_C.csv ho1_D.csv ho1_x.csv
  python score.py ho1_x.csv ho1.jsonl --baseline baseline_dev_verdicts.csv | findstr /C:"COMBINED"
  echo ===== %%M[C,D] criterion2
  python ..\tools\combine.py %%M ho2_C.csv ho2_D.csv ho2_x.csv
  python score.py ho2_x.csv ho2.jsonl --baseline ho2_base.csv | findstr /C:"COMBINED"
)
echo ===== MAJ[C,D,A] criterion1
python ..\tools\combine3.py ho1_C.csv ho1_D.csv ho1_A.csv ho1_x.csv
python score.py ho1_x.csv ho1.jsonl --baseline baseline_dev_verdicts.csv | findstr /C:"COMBINED"
echo ===== MAJ[C,D,A] criterion2
python ..\tools\combine3.py ho2_C.csv ho2_D.csv ho2_A.csv ho2_x.csv
python score.py ho2_x.csv ho2.jsonl --baseline ho2_base.csv | findstr /C:"COMBINED"
cd ..
endlocal
