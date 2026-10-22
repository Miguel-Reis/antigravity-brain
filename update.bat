@echo off
chcp 65001 >nul
echo ====================================================================
echo  🔄 A verificar e instalar atualizacoes do Antigravity Brain v2.4...
echo ====================================================================
python "%~dp0auto_updater.py"
python "%~dp0install.py" --silent
echo.
echo ✅ Concluido!
pause
