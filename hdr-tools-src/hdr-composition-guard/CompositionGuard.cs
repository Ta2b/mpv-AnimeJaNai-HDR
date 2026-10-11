using System;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

internal sealed class CompositionGuard : Form
{
	private struct Rect
	{
		public int Left;

		public int Top;

		public int Right;

		public int Bottom;
	}

	private struct MonitorInfo
	{
		public int Size;

		public Rect Monitor;

		public Rect Work;

		public uint Flags;
	}

	private readonly Process parent;

	private readonly int parentId;

	private readonly Timer timer = new Timer();

	protected override bool ShowWithoutActivation => true;

	protected override CreateParams CreateParams
	{
		get
		{
			CreateParams createParams = ((Form)this).CreateParams;
			createParams.ExStyle |= 0x80800A0;
			return createParams;
		}
	}

	[DllImport("user32.dll")]
	private static extern IntPtr GetForegroundWindow();

	[DllImport("user32.dll")]
	private static extern uint GetWindowThreadProcessId(IntPtr h, out uint id);

	[DllImport("user32.dll")]
	private static extern bool GetWindowRect(IntPtr h, out Rect r);

	[DllImport("user32.dll")]
	private static extern bool IsIconic(IntPtr h);

	[DllImport("user32.dll")]
	private static extern IntPtr MonitorFromWindow(IntPtr h, uint flags);

	[DllImport("user32.dll", CharSet = CharSet.Auto)]
	private static extern bool GetMonitorInfo(IntPtr h, ref MonitorInfo m);

	[DllImport("user32.dll")]
	private static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hgt, uint flags);

	[DllImport("user32.dll")]
	private static extern bool SetProcessDPIAware();

	[DllImport("user32.dll")]
	private static extern bool ShowWindow(IntPtr h, int command);

	[DllImport("user32.dll")]
	private static extern bool SetLayeredWindowAttributes(IntPtr h, uint key, byte alpha, uint flags);

	private CompositionGuard(Process process)
	{
		//IL_0003: Unknown result type (might be due to invalid IL or missing references)
		//IL_000d: Expected Obj, but got Unknown
		parent = process;
		parentId = process.Id;
		((Form)this).FormBorderStyle = (FormBorderStyle)0;
		((Form)this).ShowInTaskbar = false;
		((Form)this).StartPosition = (FormStartPosition)0;
		((Control)this).BackColor = Color.Black;
		((Form)this).Size = new Size(2, 2);
		_ = ((Control)this).Handle;
		SetLayeredWindowAttributes(((Control)this).Handle, 0u, byte.MaxValue, 2u);
		timer.Interval = 250;
		Timer val = timer;
		EventHandler eventHandler = (object param0, EventArgs param1) =>
		{
			UpdateGuard();
		};
		val.Tick += eventHandler;
		timer.Start();
	}

	protected override void WndProc(ref Message m)
	{
		if (m.Msg == 132)
		{
			m.Result = new IntPtr(-1);
		}
		else if (m.Msg == 33)
		{
			m.Result = new IntPtr(3);
		}
		else
		{
			((Form)this).WndProc(ref m);
		}
	}

	private void HideGuard()
	{
		ShowWindow(((Control)this).Handle, 0);
	}

	private void UpdateGuard()
	{
		try
		{
			if (parent.HasExited)
			{
				timer.Stop();
				Application.ExitThread();
				return;
			}
		}
		catch
		{
			timer.Stop();
			Application.ExitThread();
			return;
		}
		IntPtr foregroundWindow = GetForegroundWindow();
		GetWindowThreadProcessId(foregroundWindow, out var id);
		if (id != (uint)parentId || IsIconic(foregroundWindow) || !GetWindowRect(foregroundWindow, out var r))
		{
			HideGuard();
			return;
		}
		MonitorInfo m = new MonitorInfo
		{
			Size = Marshal.SizeOf(typeof(MonitorInfo))
		};
		if (!GetMonitorInfo(MonitorFromWindow(foregroundWindow, 2u), ref m))
		{
			HideGuard();
			return;
		}
		Rect monitor = m.Monitor;
		if (Math.Abs(r.Left - monitor.Left) > 1 || Math.Abs(r.Top - monitor.Top) > 1 || Math.Abs(r.Right - monitor.Right) > 1 || Math.Abs(r.Bottom - monitor.Bottom) > 1)
		{
			HideGuard();
		}
		else
		{
			SetWindowPos(((Control)this).Handle, new IntPtr(-1), monitor.Right - 2, monitor.Bottom - 2, 2, 2, 80u);
		}
	}

	[STAThread]
	private static void Main(string[] args)
	{
		if (args.Length != 1 || !int.TryParse(args[0], out var result))
		{
			return;
		}
		try
		{
			SetProcessDPIAware();
			using Process process = Process.GetProcessById(result);
			CompositionGuard compositionGuard = new CompositionGuard(process);
			try
			{
				Application.Run();
			}
			finally
			{
				((IDisposable)(object)compositionGuard)?.Dispose();
			}
		}
		catch
		{
		}
	}
}
