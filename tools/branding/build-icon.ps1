[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$iconRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$iconTarget = Join-Path $iconRoot 'app/static/libro-trabajo.ico'
if (Test-Path -LiteralPath $iconTarget) { throw 'El icono ya existe. Conservarlo o confirmar una regeneración con otra ruta.' }
$iconFrames = @()
foreach ($iconSize in @(16,24,32,48,64,128,256)) {
    $bitmap = [System.Drawing.Bitmap]::new($iconSize,$iconSize)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = 'AntiAlias'
    $graphics.ScaleTransform($iconSize/256.0,$iconSize/256.0)
    $navy = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#123047'))
    $mint = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#38d4bd'))
    $path = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $path.AddArc(0,0,104,104,180,90);$path.AddArc(152,0,104,104,270,90)
    $path.AddArc(152,152,104,104,0,90);$path.AddArc(0,152,104,104,90,90);$path.CloseFigure()
    $graphics.FillPath($navy,$path)
    $left=[System.Drawing.PointF[]]@([System.Drawing.PointF]::new(38,55),[System.Drawing.PointF]::new(80,50),[System.Drawing.PointF]::new(120,66),[System.Drawing.PointF]::new(120,205),[System.Drawing.PointF]::new(80,189),[System.Drawing.PointF]::new(38,195))
    $right=[System.Drawing.PointF[]]@([System.Drawing.PointF]::new(136,66),[System.Drawing.PointF]::new(176,50),[System.Drawing.PointF]::new(218,55),[System.Drawing.PointF]::new(218,195),[System.Drawing.PointF]::new(176,189),[System.Drawing.PointF]::new(136,205))
    $graphics.FillPolygon([System.Drawing.Brushes]::White,$left);$graphics.FillPolygon($mint,$right)
    $pen=[System.Drawing.Pen]::new($navy,8);$pen.StartCap='Round';$pen.EndCap='Round'
    foreach($lineY in @(86,113,140)){$graphics.DrawLine($pen,58,$lineY,101,($lineY+5))}
    $pen.Width=12;$graphics.DrawLine($pen,157,123,173,139);$graphics.DrawLine($pen,173,139,201,105)
    $stream=[System.IO.MemoryStream]::new();$bitmap.Save($stream,[System.Drawing.Imaging.ImageFormat]::Png)
    $iconFrames+= ,($stream.ToArray())
    $stream.Dispose();$pen.Dispose();$path.Dispose();$mint.Dispose();$navy.Dispose();$graphics.Dispose();$bitmap.Dispose()
}
$file=[System.IO.File]::Open($iconTarget,[System.IO.FileMode]::CreateNew)
$writer=[System.IO.BinaryWriter]::new($file)
try {
    $writer.Write([uint16]0);$writer.Write([uint16]1);$writer.Write([uint16]7)
    $offset=6+16*7;$sizes=@(16,24,32,48,64,128,256)
    for($i=0;$i -lt 7;$i++){
        $dimension=if($sizes[$i] -eq 256){0}else{$sizes[$i]}
        $writer.Write([byte]$dimension);$writer.Write([byte]$dimension);$writer.Write([byte]0);$writer.Write([byte]0)
        $writer.Write([uint16]1);$writer.Write([uint16]32);$writer.Write([uint32]$iconFrames[$i].Length);$writer.Write([uint32]$offset)
        $offset+=$iconFrames[$i].Length
    }
    foreach($frame in $iconFrames){$writer.Write([byte[]]$frame)}
} finally {$writer.Dispose();$file.Dispose()}
Write-Output 'Icono generado con 7 resoluciones (16 a 256 px).'
