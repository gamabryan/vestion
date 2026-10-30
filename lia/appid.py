"""Identidade do Vestion na barra de tarefas do Windows (AppUserModelID).

Sem ela, a janela fica agrupada com o pythonw e mostra o ícone do Python. Os atalhos levam o mesmo ID,
assim o atalho fixado na barra e a janela aberta viram um ícone só.
"""
import os
from pathlib import Path

APP_ID = "Vestion.Assistente"


def set_process_app_id() -> None:
    """Chame antes de criar qualquer janela."""
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def set_shortcut_app_id(lnk: Path) -> None:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shellcon
    store = propsys.SHGetPropertyStoreFromParsingName(str(lnk), None, shellcon.GPS_READWRITE,
                                                      propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()


def vestion_shortcuts() -> list[Path]:
    """Atalhos do Vestion: Área de Trabalho, menu Iniciar e o fixado na barra de tarefas."""
    home, appdata = Path.home(), Path(os.environ.get("APPDATA", ""))
    candidates = [home / "Desktop" / "Vestion.lnk", home / "OneDrive" / "Desktop" / "Vestion.lnk",
                  appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Vestion.lnk",
                  appdata / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "TaskBar" / "Vestion.lnk"]
    return [p for p in candidates if p.exists()]


def stamp_shortcuts() -> list[Path]:
    done = []
    for lnk in vestion_shortcuts():
        set_shortcut_app_id(lnk)
        done.append(lnk)
    return done


if __name__ == "__main__":
    for p in stamp_shortcuts():
        print("ID aplicado em", p)
