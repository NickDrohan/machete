@echo off
rem machete-cluster for GUIs and match runners that start an executable: see harness/cluster.py
py -3.13 "%~dp0cluster.py" --config "%MACHETE_CLUSTER_CONFIG%" --log "%MACHETE_CLUSTER_LOG%"
