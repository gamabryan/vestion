# Cria o atalho "Vestion" na Área de Trabalho e no menu Iniciar (e remove o antigo "Lia").
# Não coloca nada na inicialização do Windows: o Vestion só abre quando você quiser.
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
    $antigo = Join-Path $pasta "Lia.lnk"
    if (Test-Path $antigo) { Remove-Item $antigo }
    $lnk = $shell.CreateShortcut((Join-Path $pasta "Vestion.lnk"))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = "`"$script`""
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = $icon
    $lnk.Description = "Vestion - assistente de voz"
    $lnk.Save()
    Write-Host "Atalho criado em $pasta"
}
