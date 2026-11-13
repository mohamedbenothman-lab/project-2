@echo off
rem 16:00 submission in one go. Run from Project_3\ :
rem    tools\final.bat hidden\<criterion1 file>.jsonl hidden\<criterion2 file>.jsonl
rem Unzip first if needed:  powershell -command "Expand-Archive -Force hidden_cases.zip hidden"
setlocal
cd /d %~dp0..
if "%~2"=="" (echo Usage: tools\final.bat CRITERION1_CASES.jsonl CRITERION2_CASES.jsonl & exit /b 1)
if not exist "%~1" (echo Not found: %~1 & exit /b 1)
if not exist "%~2" (echo Not found: %~2 & exit /b 1)
git pull
python tools\run.py final "%~1" "%~2" || (echo RUN FAILED - nothing committed & exit /b 1)
for %%F in (criterion1_run1 criterion1_run2 criterion2_run1 criterion2_run2) do (
  if not exist submission\%%F.csv (echo MISSING submission\%%F.csv - nothing committed & exit /b 1)
)
echo.
echo === rows per file (header + one per case)
for %%F in (submission\criterion*.csv) do (find /c /v "" "%%F")
echo === consistency (same verdict share) between the two runs
python -c "import csv;r=lambda p:{x['case_id']:(x['original'],x['edited']) for x in csv.DictReader(open(p))};[print(n, round(sum(a[k]==b.get(k) for k in a)/len(a),3)) for n,a,b in (('criterion1',r('submission/criterion1_run1.csv'),r('submission/criterion1_run2.csv')),('criterion2',r('submission/criterion2_run1.csv'),r('submission/criterion2_run2.csv')))]"
cd ..
git add Project_3/submission/criterion1_run1.csv Project_3/submission/criterion1_run2.csv Project_3/submission/criterion2_run1.csv Project_3/submission/criterion2_run2.csv
git commit -m "submission: hidden runs (frozen judge, claude-haiku-4.5)"
git push
echo DONE. Check GitHub: branch project-3, folder Project_3/submission
endlocal
