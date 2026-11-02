# The small application icon is drawn from these editable vector primitives.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$image = New-Object System.Drawing.Bitmap 64,64
$graphics = [System.Drawing.Graphics]::FromImage($image)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$purple = [System.Drawing.ColorTranslator]::FromHtml('#6854d9')
$brush = New-Object System.Drawing.SolidBrush $purple
$graphics.FillRectangle($brush, 0, 0, 64, 64)
$graphics.FillRectangle([System.Drawing.Brushes]::Lavender, 11, 9, 36, 42)
$graphics.FillRectangle([System.Drawing.Brushes]::White, 18, 15, 36, 42)
$pen = New-Object System.Drawing.Pen $purple,3
$graphics.DrawLine($pen, 26, 29, 46, 29)
$graphics.DrawLine($pen, 26, 37, 46, 37)
$graphics.DrawLine($pen, 26, 45, 39, 45)
$stream = New-Object System.IO.MemoryStream
$image.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
$bytes = $stream.ToArray()
$path = Join-Path $PSScriptRoot '../packaging/windows/ankicard.ico'
$writer = New-Object System.IO.BinaryWriter ([System.IO.File]::Create($path))
try {
    $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]1)
    $writer.Write([byte]64); $writer.Write([byte]64); $writer.Write([byte]0); $writer.Write([byte]0)
    $writer.Write([uint16]1); $writer.Write([uint16]32)
    $writer.Write([uint32]$bytes.Length); $writer.Write([uint32]22); $writer.Write($bytes)
} finally {
    $writer.Dispose(); $stream.Dispose(); $graphics.Dispose()
    $image.Dispose(); $pen.Dispose(); $brush.Dispose()
}
