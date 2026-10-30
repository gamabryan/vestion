# Cria o atalho "Lia" na Área de Trabalho e no menu Iniciar.
# Não coloca nada na inicialização do Windows: a Lia só abre quando você quiser.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$script = Join-Path $root "Lia.pyw"
$icon = Join-Path $root "lia\ui\lia.ico"

& (Join-Path $root ".venv\Scripts\python.exe") -c "import sys; sys.path.insert(0, r'$root'); from lia.tray import save_ico; save_ico()"

$shell = New-Object -ComObject WScript.Shell
$destinos = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($pasta in $destinos) {
    $lnk = $shell.CreateShortcut((Join-Path $pasta "Lia.lnk"))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = "`"$script`""
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = $icon
    $lnk.Description = "Lia - assistente de voz"
    $lnk.Save()
    Write-Host "Atalho criado em $pasta"
}
