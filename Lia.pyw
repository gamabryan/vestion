"""Abre a Lia sem janela de console (use o atalho criado por scripts/criar_atalho.ps1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lia.app import main

main()
