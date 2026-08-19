@echo off
REM ===================================================================
REM  Arranque automatico del agente. Uno por maquina.
REM
REM  INSTALACION:
REM  1. Editar los cinco SET de abajo con los datos de ESTA maquina
REM  2. Guardar como iniciar-agente.bat en C:\claude-agent\
REM  3. Tecla Windows + R  ->  escribir  shell:startup  ->  Enter
REM  4. Copiar un ACCESO DIRECTO de este .bat dentro de esa carpeta
REM
REM  Desde el proximo reinicio arranca solo al iniciar sesion.
REM ===================================================================

SET DEVICE_ID=poner-el-deviceId-de-esta-maquina
SET CLAUDE_BIN=C:\Users\NOMBRE\.local\bin\claude.exe
SET AGENT_TOKEN=poner-el-token-compartido
SET MACHINE_NAME=PC-1
SET MODEL=claude-sonnet-5

cd /d C:\claude-agent

REM Log rotativo simple: guarda la salida para poder revisar fallas.
python agent.py >> agente.log 2>&1
