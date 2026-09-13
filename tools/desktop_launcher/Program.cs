using System.Diagnostics;
using System.Net.Http;
using System.Text.RegularExpressions;

namespace CentroOperativoLauncher;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new LauncherForm());
    }
}

internal sealed class LauncherForm : Form
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(3) };
    private readonly Label _status = new();
    private readonly TextBox _log = new();
    private readonly Button _start = new();
    private readonly Button _open = new();
    private readonly Button _stop = new();
    private string? _docker;
    private string? _projectRoot;
    private bool _starting;

    public LauncherForm()
    {
        Text = "Libro de Trabajo · Centro Operativo";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(650, 430);
        ClientSize = new Size(760, 500);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;

        var title = new Label
        {
            Text = "Libro de Trabajo",
            AutoSize = true,
            Font = new Font("Segoe UI", 18, FontStyle.Bold),
            Location = new Point(24, 20),
        };
        var subtitle = new Label
        {
            Text = "Centro Operativo · Lanzador seguro para Docker/PostgreSQL",
            AutoSize = true,
            ForeColor = Color.DimGray,
            Location = new Point(27, 57),
        };
        _status.Text = "Comprobando el entorno…";
        _status.AutoSize = true;
        _status.Location = new Point(27, 88);
        _status.Font = new Font("Segoe UI", 10, FontStyle.Bold);

        _start.Text = "Iniciar / actualizar";
        _start.AutoSize = true;
        _start.Location = new Point(24, 122);
        _start.Click += async (_, _) => await StartAsync(true);

        _open.Text = "Abrir aplicación";
        _open.AutoSize = true;
        _open.Location = new Point(176, 122);
        _open.Click += (_, _) => OpenBrowser();

        _stop.Text = "Detener servicios";
        _stop.AutoSize = true;
        _stop.Location = new Point(322, 122);
        _stop.Click += async (_, _) => await StopAsync();

        _log.Multiline = true;
        _log.ReadOnly = true;
        _log.ScrollBars = ScrollBars.Vertical;
        _log.BackColor = Color.FromArgb(248, 249, 250);
        _log.Font = new Font("Consolas", 9);
        _log.Location = new Point(24, 170);
        _log.Size = new Size(710, 295);
        _log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;

        Controls.AddRange([title, subtitle, _status, _start, _open, _stop, _log]);
        // Abrir el lanzador no debe reconstruir una entrega automáticamente.
        // La actualización queda reservada al botón explícito.
        Shown += async (_, _) => await StartAsync(false);
    }

    private async Task StartAsync(bool rebuild)
    {
        if (_starting) return;
        _starting = true;
        SetButtons(false);
        try
        {
            _projectRoot = FindProjectRoot();
            if (_projectRoot is null)
                throw new InvalidOperationException("No se encontró compose.yaml. Coloque este ejecutable dentro de la carpeta del proyecto o en una subcarpeta.");
            Log($"Proyecto: {_projectRoot}");

            _docker = await ResolveDockerAsync();
            if (_docker is null)
                throw new InvalidOperationException("No se encontró Docker CLI. Abra Docker Desktop o instálelo antes de usar este lanzador.");

            if (!await EnsureDockerReadyAsync())
                throw new InvalidOperationException("Docker Desktop no llegó a estar disponible. Abra Docker Desktop y vuelva a pulsar Iniciar.");

            var arguments = rebuild
                ? new[] { "compose", "up", "-d", "--build", "app" }
                : new[] { "compose", "up", "-d", "app" };
            Log(rebuild ? "Iniciando y reconstruyendo app…" : "Iniciando servicios Docker…");
            var compose = await RunDockerAsync(arguments);
            if (compose.ExitCode != 0)
                throw new InvalidOperationException("Docker Compose no pudo iniciar app. Revise el registro mostrado.");

            Log("Esperando la comprobación de salud…");
            if (!await WaitForHealthAsync(TimeSpan.FromSeconds(90)))
                throw new InvalidOperationException("La aplicación no respondió saludablemente en 90 segundos.");

            SetStatus("Centro Operativo disponible", Color.DarkGreen);
            Log("Listo: http://127.0.0.1:8000/");
            OpenBrowser();
        }
        catch (Exception error)
        {
            SetStatus("No se pudo iniciar", Color.DarkRed);
            Log($"ERROR: {error.Message}");
        }
        finally
        {
            _starting = false;
            SetButtons(true);
        }
    }

    private async Task StopAsync()
    {
        if (_projectRoot is null || _docker is null)
        {
            Log("No hay un proyecto Docker detectado para detener.");
            return;
        }
        SetButtons(false);
        try
        {
            Log("Deteniendo servicios sin eliminar volúmenes…");
            var result = await RunDockerAsync(["compose", "stop", "app", "backup", "db"]);
            if (result.ExitCode != 0) throw new InvalidOperationException("Docker Compose devolvió un error al detener.");
            SetStatus("Servicios detenidos", Color.DarkOrange);
            Log("Los volúmenes y los datos se conservaron.");
        }
        catch (Exception error)
        {
            SetStatus("No se pudo detener", Color.DarkRed);
            Log($"ERROR: {error.Message}");
        }
        finally
        {
            SetButtons(true);
        }
    }

    private async Task<string?> ResolveDockerAsync()
    {
        foreach (var candidate in new[]
        {
            "docker",
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "DockerDesktop", "resources", "bin", "docker.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Docker", "Docker", "resources", "bin", "docker.exe"),
        })
        {
            var result = await RunProcessAsync(candidate, ["version", "--format", "{{.Client.Version}}"], _projectRoot!, TimeSpan.FromSeconds(8));
            if (result.ExitCode == 0) return candidate;
        }
        return null;
    }

    private async Task<bool> EnsureDockerReadyAsync()
    {
        var result = await RunDockerAsync(["info"]);
        if (result.ExitCode == 0) return true;

        foreach (var desktop in DockerDesktopCandidates())
        {
            if (!File.Exists(desktop)) continue;
            Log("Docker Desktop no estaba listo; abriéndolo…");
            Process.Start(new ProcessStartInfo { FileName = desktop, UseShellExecute = true });
            for (var attempt = 0; attempt < 60; attempt++)
            {
                await Task.Delay(2000);
                result = await RunDockerAsync(["info"]);
                if (result.ExitCode == 0) return true;
            }
            break;
        }
        return false;
    }

    private IEnumerable<string> DockerDesktopCandidates()
    {
        yield return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "DockerDesktop", "Docker Desktop.exe");
        yield return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Docker", "Docker", "Docker Desktop.exe");
    }

    private async Task<bool> WaitForHealthAsync(TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                using var response = await Http.GetAsync("http://127.0.0.1:8000/health");
                if (response.IsSuccessStatusCode) return true;
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }
            await Task.Delay(1000);
        }
        return false;
    }

    private async Task<(int ExitCode, string Output)> RunDockerAsync(string[] arguments)
    {
        return await RunProcessAsync(_docker!, arguments, _projectRoot!, TimeSpan.FromMinutes(5));
    }

    private static async Task<(int ExitCode, string Output)> RunProcessAsync(string executable, string[] arguments, string workingDirectory, TimeSpan timeout)
    {
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = executable,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            },
        };
        foreach (var argument in arguments) process.StartInfo.ArgumentList.Add(argument);
        try
        {
            if (!process.Start()) return (-1, "No se pudo iniciar el proceso.");
        }
        catch (Exception error)
        {
            return (-1, error.Message);
        }

        var standardOutput = process.StandardOutput.ReadToEndAsync();
        var standardError = process.StandardError.ReadToEndAsync();
        using var cancellation = new CancellationTokenSource(timeout);
        try
        {
            await process.WaitForExitAsync(cancellation.Token);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            return (-1, "Tiempo de espera agotado.");
        }
        var output = $"{await standardOutput}\n{await standardError}".Trim();
        return (process.ExitCode, Scrub(output));
    }

    private static string Scrub(string value)
    {
        return Regex.Replace(value, "(?i)(PASSWORD|SECRET|TOKEN)=\\S+", "$1=<oculto>");
    }

    private string? FindProjectRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        for (var level = 0; level < 10 && directory is not null; level++, directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "compose.yaml"))) return directory.FullName;
        }
        return null;
    }

    private void OpenBrowser()
    {
        Process.Start(new ProcessStartInfo { FileName = "http://127.0.0.1:8000/", UseShellExecute = true });
    }

    private void SetButtons(bool enabled)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => SetButtons(enabled));
            return;
        }
        _start.Enabled = enabled;
        _open.Enabled = enabled;
        _stop.Enabled = enabled;
    }

    private void SetStatus(string text, Color color)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => SetStatus(text, color));
            return;
        }
        _status.Text = text;
        _status.ForeColor = color;
    }

    private void Log(string message)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => Log(message));
            return;
        }
        _log.AppendText($"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}");
    }
}
