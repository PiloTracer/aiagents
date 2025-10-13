@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM DLV2 stack manager for docker-compose.yml
REM Features (simplified to align with ref.bat):
REM  1) Start
REM  2) Stop
REM  3) Reset (remove only this project's Docker resources)
REM  4) Restart
REM  5) Restore DB volumes backup [stack remains stopped]
REM  6) Backup DB volumes to tar.gz
REM  7) View logs (ESC to exit)
REM  0) Exit

REM Change working directory to repo root (script is expected in bin\)
pushd "%~dp0.." >nul 2>&1

set "COMPOSE_FILE=docker-compose.yml"
set "PROJECT_NAME=dlv2"
set "BACKUP_DIR=%CD%\backups"
set "STACK_LABEL=com.docker.compose.project=%PROJECT_NAME%"
set "VOLUME_SUFFIXES=dbdata dbragdata dbragsnapshots"

call :detect_compose || goto :fatal
call :check_docker || goto :fatal

REM Guard: ensure compose file exists in repo root and is valid for this project
if not exist "%COMPOSE_FILE%" (
  echo [FATAL] Compose file not found: "%COMPOSE_FILE%" in %CD%
  goto :fatal
)
call :compose_cmd config >nul 2>&1 || (
  echo [FATAL] Invalid compose configuration for project %PROJECT_NAME%
  goto :fatal
)

REM Guard: ensure this is the DLV2 repository (avoid touching other stacks)
if not exist "Dockerfile.pg" (
  echo [FATAL] DLV2 marker file missing: Dockerfile.pg
  goto :fatal
)
if not exist "backend\Dockerfile.dev" (
  echo [FATAL] DLV2 marker file missing: backend\Dockerfile.dev
  goto :fatal
)
if not exist "frontend\Dockerfile.dev" (
  echo [FATAL] DLV2 marker file missing: frontend\Dockerfile.dev
  goto :fatal
)

:menu
cls
@echo off
set "RESTORE_CTX="
call :status_indicator
REM Flush any stray keypresses before reading choice (from prior Ctrl+C/pause)
powershell -NoProfile -Command "$Host.UI.RawUI.FlushInputBuffer()" >nul 2>&1
echo ===============================================
echo   DLV2 Stack Control - %DATE% %TIME:~0,8%
echo   Project: %PROJECT_NAME%   Compose: %COMPOSE_FILE%
echo   Backups: %BACKUP_DIR%
echo   Status : %STATUS_ICON% %STATUS_TEXT%  [%RUN_COUNT%/%SVC_TOTAL%]
echo ===============================================
echo(
echo   1) Start (docker compose up -d)
echo   2) Stop (docker compose down)
echo   3) Reset (remove this stack only)
echo   4) Restart (down + up)
echo   5) Restore DB volumes from backup (.tar.gz)
echo   6) Backup DB volumes (as .tar.gz)
echo   7) View Logs  (ESC to exit)
echo   90) Maintenance off (N/A)
echo   99) Refresh menu
echo   0) Exit
echo(
echo   Restore tip: enter timestamp YYYYMMDD-HHmmss to restore
echo   Example: 20251007-203647 (used by option 5)
set "_choice="
set /p _choice=Select option and press ENTER: 
REM Trim spaces and common stray chars
set "_choice=%_choice: =%"
set "_choice=%_choice:)=%"
set "_choice=%_choice:(=%"

if "%_choice%"=="1" goto :do_start
if "%_choice%"=="2" goto :stop
if "%_choice%"=="3" goto :reset
if "%_choice%"=="4" goto :restart
if "%_choice%"=="5" ( set "RESTORE_CTX=vol" & goto :restore_volumes )
if "%_choice%"=="6" goto :backup
if "%_choice%"=="7" goto :viewlog
if "%_choice%"=="90" goto :maintenance_off
if "%_choice%"=="99" goto :menu
if "%_choice%"=="0" goto :bye

echo(
echo [WARN] Invalid selection "%_choice%"
call :pause
goto :menu

:do_start
echo(
echo [INFO] Starting stack
REM Ensure a clean environment (avoid any residual restore vars)
set "TS_INPUT="
set "DB_DUMP="
set "GL_FILE="
set "PG_FILE="
set "_DBRESTFAIL="
set "_GLFAIL="
set "_MDFail="
set "_DBFAIL="
set "_DROPFAIL="

REM Ensure project-namespaced volumes exist without overwriting (Compose creates if missing)
for %%V in ("%PROJECT_NAME%_dbdata") do (
  docker volume inspect %%~V >nul 2>&1
  if errorlevel 1 (
    echo [INFO] Creating external volume %%~V
    docker volume create %%~V >nul 2>&1 || (echo [ERROR] Could not create volume %%~V & call :pause & goto :menu)
  ) else (
    echo [INFO] External volume %%~V exists Skipping creation
)
)

call :compose_cmd up -d --remove-orphans
if errorlevel 1 (
  echo [ERROR] Failed to start
  call :pause
  goto :menu
)
call :compose_cmd ps
echo [OK] Stack started
call :pause
goto :menu

:stop
echo(
echo [INFO] Stopping stack
REM Clear any restore context/vars to avoid cross-step leakage
set "RESTORE_CTX="
set "TS_INPUT="
set "DB_DUMP="
set "GL_FILE="
set "PG_FILE="
set "_DBRESTFAIL="
set "_GLRESTFAIL="
set "_MDFail="
set "_DBFAIL="
set "_DROPFAIL="

call :compose_cmd down --remove-orphans -t 10
if errorlevel 1 echo [WARN] compose down finished with warnings or failed

call :compose_cmd ps

set "_RUN_LEFT=0"
for /f "tokens=* delims=" %%r in ('docker ps --filter "label=%STACK_LABEL%" --format "{{.ID}}" 2^>nul') do set /a _RUN_LEFT+=1
if %_RUN_LEFT% gtr 0 (
  echo [WARN] Some containers may still be running for project %PROJECT_NAME%
) else (
  echo [OK] Stack stopped
)
call :pause
goto :menu

:restart
echo(
echo [INFO] Restarting stack
echo [INFO] Stopping stack
call :compose_cmd down --remove-orphans -t 10
echo [INFO] Starting stack
call :compose_cmd up -d --remove-orphans
if errorlevel 1 (
  echo [ERROR] Failed to start after restart
  call :pause
  goto :menu
)
call :compose_cmd ps
echo [OK] Stack restarted
call :pause
goto :menu
:reset
echo(
echo [INFO] This will remove containers, images, volumes, and networks for project "%PROJECT_NAME%" only
echo        Other Docker stacks will not be affected
call :confirm "Proceed with project reset? (Y/N) "
if errorlevel 2 (echo [INFO] Cancelled & call :pause & goto :menu)

echo [INFO] Bringing project down and removing compose-managed resources
call :compose_cmd down -v --rmi all --remove-orphans || echo [WARN] compose down finished with warnings

echo [INFO] Removing any leftover project volumes
for /f %%v in ('docker volume ls -q --filter "label=%STACK_LABEL%" 2^>nul') do docker volume rm -f "%%v" >nul 2>&1
REM Also remove the known named volume in case it was created externally without labels
docker volume rm -f "%PROJECT_NAME%_dbdata" >nul 2>&1

echo [INFO] Removing any leftover project networks
for /f %%n in ('docker network ls -q --filter "label=%STACK_LABEL%" 2^>nul') do docker network rm "%%n" >nul 2>&1

echo [INFO] Removing any leftover project images
for /f %%i in ('docker images -q --filter "label=%STACK_LABEL%" 2^>nul') do docker rmi -f "%%i" >nul 2>&1

set "_LEFT=0"
for /f %%c in ('docker ps -a -q --filter "label=%STACK_LABEL%" 2^>nul') do set /a _LEFT+=1
for /f %%v in ('docker volume ls -q --filter "label=%STACK_LABEL%" 2^>nul') do set /a _LEFT+=1
for /f %%n in ('docker network ls -q --filter "label=%STACK_LABEL%" 2^>nul') do set /a _LEFT+=1
for /f %%i in ('docker images -q --filter "label=%STACK_LABEL%" 2^>nul') do set /a _LEFT+=1

if %_LEFT% gtr 0 (
  echo [WARN] Some project resources could not be removed (possibly in use)
) else (
  echo [OK] Project reset complete
)
call :pause
goto :menu

:backup
echo(
echo [INFO] Preparing backup directory: "%BACKUP_DIR%"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%" 2>nul
if errorlevel 1 (echo [ERROR] Cannot create backup directory & call :pause & goto :menu)

call :timestamp
set "TS=%_TS%"

echo [INFO] Ensuring stack is stopped for a consistent backup
call :compose_cmd down >nul 2>&1

set "SUCCESS_LIST="
set "WARN_LIST="
set "FAILURE="

for %%S in (%VOLUME_SUFFIXES%) do (
  set "VOL_NAME=%PROJECT_NAME%_%%S"
  call :backup_volume "%%S" "!VOL_NAME!" "%TS%" "%BACKUP_DIR%"
  set "RC=!errorlevel!"
  if "!RC!"=="0" (
    set "SUCCESS_LIST=!SUCCESS_LIST! %%S"
  ) else if "!RC!"=="1" (
    set "WARN_LIST=!WARN_LIST! %%S"
  ) else (
    set "FAILURE=1"
  )
)

if defined FAILURE (
  echo [ERROR] One or more volume backups failed. See messages above.
  call :pause
  goto :menu
)

if not defined SUCCESS_LIST (
  echo [WARN] No volumes were backed up. Missing volumes:%WARN_LIST%
  call :pause
  goto :menu
)

if defined WARN_LIST (
  echo [WARN] Skipped volumes (not found):%WARN_LIST%
)

echo [OK] Backup completed. Archives created for:%SUCCESS_LIST%
echo [INFO] Files stored in "%BACKUP_DIR%" as ^<suffix^>-%TS%.tar.gz
echo [INFO] Stack remains stopped Use option 1 to start
call :pause
goto :menu

:restore_volumes
echo(
call :status_indicator
if %RUN_COUNT% gtr 0 (
  echo [INFO] Stopping running services
  call :compose_cmd down --remove-orphans -t 10 >nul 2>&1
)

echo [INFO] This will restore volumes from backups; stack stays stopped
echo        Existing data in the target volumes will be overwritten

if not exist "%BACKUP_DIR%" (
  echo [ERROR] Backup directory not found: "%BACKUP_DIR%"
  call :pause & goto :menu
)

set "LATEST_TS="
for /f %%i in ('powershell -NoProfile -Command "$p='%BACKUP_DIR%'; $f=Get-ChildItem -Path $p -Filter 'dbdata-*.tar.gz' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){ ($f.Name -replace '^dbdata-|\.tar\.gz$','') }"') do set "LATEST_TS=%%i"
if not defined LATEST_TS (
  echo [ERROR] No backups found in "%BACKUP_DIR%"
  call :pause & goto :menu
)
echo(
set "TS_INPUT="
set /p TS_INPUT=Enter backup timestamp [Default: %LATEST_TS%]: 
if not defined TS_INPUT set "TS_INPUT=%LATEST_TS%"

REM Validate timestamp format (YYYYMMDD-HHmmss)
echo [INFO] Validating timestamp format
ver >nul
echo %TS_INPUT%| findstr /R "^[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]$" >nul
if errorlevel 1 (
  echo [ERROR] Invalid or empty timestamp format Must be YYYYMMDD-HHmmss for example 20251008-165000
  call :pause & goto :menu
)
echo [INFO] Timestamp format is ok

set "MISSING_LIST="
set "RESTORE_LIST="
for %%S in (%VOLUME_SUFFIXES%) do (
  set "ARCHIVE_%%S=%%S-%TS_INPUT%.tar.gz"
  if exist "%BACKUP_DIR%\!ARCHIVE_%%S!" (
    set "RESTORE_LIST=!RESTORE_LIST! %%S"
  ) else (
    set "MISSING_LIST=!MISSING_LIST! %%S"
  )
  set "VOL_NAME_%%S=%PROJECT_NAME%_%%S"
)

if defined MISSING_LIST (
  echo [ERROR] Missing backup archives for:%MISSING_LIST%
  call :pause & goto :menu
)

echo(
echo Selected timestamp %TS_INPUT%
echo   Will restore volumes:%RESTORE_LIST%
call :confirm "Proceed with restore? (Y/N) "
if errorlevel 2 (echo [INFO] Cancelled & call :pause & goto :menu)

echo [INFO] Stopping stack before restore
call :compose_cmd down

call :ensure_image alpine || (echo [ERROR] Docker base image not available & call :pause & goto :menu)

echo [INFO] Verifying backup files are readable inside Docker
for %%S in (%VOLUME_SUFFIXES%) do (
  set "ARCHIVE=!ARCHIVE_%%S!"
  docker run --rm -v "%BACKUP_DIR%:/backup:ro" alpine sh -lc "test -f /backup/!ARCHIVE! && echo found !ARCHIVE!" || (
    echo [ERROR] Cannot access !ARCHIVE! inside Docker Ensure Docker Desktop file sharing allows the drive for "%BACKUP_DIR%"
    call :pause & goto :menu
  )
)

echo [INFO] Recreating empty volumes where applicable
for %%S in (%VOLUME_SUFFIXES%) do (
  set "VOL=!VOL_NAME_%%S!"
  docker volume rm -f "!VOL!" >nul 2>&1
  docker volume create "!VOL!" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Could not create volume !VOL!
    call :pause & goto :menu
  )
)

for %%S in (%VOLUME_SUFFIXES%) do (
  set "VOL=!VOL_NAME_%%S!"
  set "ARCHIVE=!ARCHIVE_%%S!"
  call :restore_volume "%%S" "!VOL!" "!ARCHIVE!" "%BACKUP_DIR%"
  if errorlevel 1 (
    goto :restore_fail
  )
)

:restore_success
echo [OK] Restore completed for:%RESTORE_LIST%
echo [INFO] Use option 1 to start services when ready
call :pause
goto :menu

:restore_fail
echo [ERROR] Restore aborted due to errors above
call :pause
goto :menu

:viewlog
cls
echo Displaying logs (Exit with Ctrl+C, then press any key)
echo(

set "_HAS_PROJ=0"
for /f "tokens=* delims=" %%r in ('docker ps -a -q --filter "label=%STACK_LABEL%" 2^>nul') do set "_HAS_PROJ=1"

if "%_HAS_PROJ%"=="1" (
  call :compose_cmd logs --tail=100 -f
) else (
  echo [ERROR] No containers found for this stack Use option 1 to start
)

echo(
pause >nul
goto :menu

:maintenance_off
echo(
echo [INFO] Maintenance toggle not applicable for this stack
call :pause
goto :menu
:confirm
REM Usage: call :confirm "Prompt here"  -> errorlevel 1 = Yes, 2 = No
setlocal
set "_prompt=%~1"
:_ask
choice /C YN /N /M "%_prompt%"
endlocal & set "_ans=%errorlevel%"
exit /b %_ans%

:timestamp
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd-HHmmss')"') do set "_TS=%%i"
exit /b 0

:check_docker
docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker daemon not reachable Ensure Docker Desktop is running
  exit /b 1
)
exit /b 0

:detect_compose
REM Prefer Docker Compose V2 plugin
docker compose version >nul 2>&1
if not errorlevel 1 (
  set "COMPOSE_EXE=docker"
  set "COMPOSE_SUB=compose"
  exit /b 0
)
REM Fallback to docker-compose (V1)
docker-compose version >nul 2>&1
if not errorlevel 1 (
  set "COMPOSE_EXE=docker-compose"
  set "COMPOSE_SUB="
  exit /b 0
)
echo [ERROR] Neither "docker compose" nor "docker-compose" is available in PATH
exit /b 1

:compose_cmd
REM Pass-through wrapper so we can call plugin or classic uniformly
if defined COMPOSE_SUB (
  "%COMPOSE_EXE%" %COMPOSE_SUB% -p "%PROJECT_NAME%" -f "%COMPOSE_FILE%" %*
) else (
  "%COMPOSE_EXE%" -p "%PROJECT_NAME%" -f "%COMPOSE_FILE%" %*
)
exit /b %errorlevel%

:status_indicator
set "STATUS_ICON=[STOP]"
set "STATUS_TEXT=Stopped"
set "RUN_COUNT=0"
set "SVC_TOTAL=0"

if defined COMPOSE_SUB (
  for /f "tokens=* delims=" %%s in ('%COMPOSE_EXE% %COMPOSE_SUB% -p %PROJECT_NAME% -f %COMPOSE_FILE% config --services 2^>nul') do (
    set /a SVC_TOTAL+=1
  )
) else (
  for /f "tokens=* delims=" %%s in ('%COMPOSE_EXE% -p %PROJECT_NAME% -f %COMPOSE_FILE% config --services 2^>nul') do (
    set /a SVC_TOTAL+=1
  )
)

for /f "tokens=* delims=" %%r in ('docker ps --filter "label=%STACK_LABEL%" --filter "status=running" --format "{{.ID}}" 2^>nul') do set /a RUN_COUNT+=1

if %SVC_TOTAL%==0 (
  for /f "tokens=* delims=" %%a in ('docker ps -a --filter "label=%STACK_LABEL%" --format "{{.ID}}" 2^>nul') do set /a SVC_TOTAL+=1
)

if %RUN_COUNT% gtr 0 (
  if %SVC_TOTAL% gtr 0 (
    if %RUN_COUNT% geq %SVC_TOTAL% (
      set "STATUS_ICON=[RUN ]"
      set "STATUS_TEXT=Running"
    ) else (
      set "STATUS_ICON=[PART]"
      set "STATUS_TEXT=Partial"
    )
  ) else (
    set "STATUS_ICON=[RUN ]"
    set "STATUS_TEXT=Running"
  )
) else (
  set "STATUS_ICON=[STOP]"
  set "STATUS_TEXT=Stopped"
)
exit /b 0

:pause
echo(
pause
exit /b 0

:fatal
echo(
echo [FATAL] Unable to initialize Aborting
popd >nul 2>&1
endlocal
exit /b 1

:bye
popd >nul 2>&1
endlocal
exit 0

:ensure_image
setlocal
set "_img=%~1"
docker image inspect "%_img%" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Pulling Docker image %_img%
  docker pull "%_img%"
  if errorlevel 1 (
    endlocal & exit /b 1
  )
)
endlocal & exit /b 0

:backup_volume
setlocal
set "SUFFIX=%~1"
set "VOLUME=%~2"
set "TS=%~3"
set "BACKUP_DIR=%~4"
set "ARCHIVE=%SUFFIX%-%TS%.tar.gz"

docker volume inspect "%VOLUME%" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Volume "%VOLUME%" not found Skipping %SUFFIX% backup
  endlocal & exit /b 1
)

echo [INFO] Backing up %SUFFIX% volume "%VOLUME%" to %ARCHIVE%
docker run --rm -v "%VOLUME%:/volume" -v "%BACKUP_DIR%:/backup" alpine sh -c "tar czf /backup/%ARCHIVE% -C /volume ."
if errorlevel 1 (
  echo [ERROR] %SUFFIX% backup failed
  endlocal & exit /b 2
)

echo [OK] %SUFFIX% volume archived as %ARCHIVE%
endlocal & exit /b 0

:restore_volume
setlocal
set "SUFFIX=%~1"
set "VOLUME=%~2"
set "ARCHIVE=%~3"
set "BACKUP_DIR=%~4"

echo [INFO] Restoring %SUFFIX% from "%ARCHIVE%"
docker run --rm -v "%VOLUME%:/volume" -v "%BACKUP_DIR%:/backup" alpine sh -lc "set -ex; rm -rf /volume/* /volume/.[!.]* /volume/..?* 2>/dev/null || true; tar xzf /backup/%ARCHIVE% -C /volume"
if errorlevel 1 (
  echo [ERROR] %SUFFIX% restore failed from %ARCHIVE%
  endlocal & exit /b 1
)

echo [OK] %SUFFIX% volume restored from %ARCHIVE%
endlocal & exit /b 0
