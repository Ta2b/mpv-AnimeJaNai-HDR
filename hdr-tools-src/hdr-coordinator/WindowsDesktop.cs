using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;

public class WindowsDesktop : IDesktop
{
	private struct Luid
	{
		public uint Low;

		public int High;
	}

	private struct Source
	{
		public Luid Adapter;

		public uint Id;

		public uint Index;

		public uint Flags;
	}

	private struct Target
	{
		public Luid Adapter;

		public uint Id;

		public uint Index;

		public uint Technology;

		public uint Rotation;

		public uint Scaling;

		public uint Numerator;

		public uint Denominator;

		public uint Scanline;

		public int Available;

		public uint Flags;
	}

	private struct PathInfo
	{
		public Source Source;

		public Target Target;

		public uint Flags;
	}

	[DllImport("user32.dll")]
	private static extern int GetDisplayConfigBufferSizes(uint flags, out uint paths, out uint modes);

	[DllImport("user32.dll")]
	private static extern int QueryDisplayConfig(uint flags, ref uint paths, [Out] PathInfo[] info, ref uint modes, IntPtr modeInfo, IntPtr topology);

	[DllImport("user32.dll")]
	private static extern int DisplayConfigGetDeviceInfo(IntPtr packet);

	[DllImport("user32.dll")]
	private static extern int DisplayConfigSetDeviceInfo(IntPtr packet);

	private static IntPtr Packet(Display d, int type, int size)
	{
		IntPtr intPtr = Marshal.AllocHGlobal(size);
		Marshal.Copy(new byte[size], 0, intPtr, size);
		Marshal.WriteInt32(intPtr, 0, type);
		Marshal.WriteInt32(intPtr, 4, size);
		Marshal.WriteInt32(intPtr, 8, (int)d.Low);
		Marshal.WriteInt32(intPtr, 12, d.High);
		Marshal.WriteInt32(intPtr, 16, (int)d.Id);
		return intPtr;
	}

	public static List<Display> Displays()
	{
		for (int i = 0; i < 3; i++)
		{
			int displayConfigBufferSizes = GetDisplayConfigBufferSizes(2u, out var paths, out var modes);
			if (displayConfigBufferSizes != 0)
			{
				throw new Exception("GetDisplayConfigBufferSizes=" + displayConfigBufferSizes);
			}
			PathInfo[] array = new PathInfo[paths];
			IntPtr intPtr = Marshal.AllocHGlobal(checked((int)modes * 64));
			try
			{
				displayConfigBufferSizes = QueryDisplayConfig(2u, ref paths, array, ref modes, intPtr, IntPtr.Zero);
				switch (displayConfigBufferSizes)
				{
				case 122:
					break;
				default:
					throw new Exception("QueryDisplayConfig=" + displayConfigBufferSizes);
				case 0:
				{
					List<Display> list = new List<Display>();
					for (int j = 0; j < paths; j++)
					{
						Target target = array[j].Target;
						Display d = new Display
						{
							Low = target.Adapter.Low,
							High = target.Adapter.High,
							Id = target.Id
						};
						IntPtr intPtr2 = Packet(d, 2, 420);
						try
						{
							displayConfigBufferSizes = DisplayConfigGetDeviceInfo(intPtr2);
							if (displayConfigBufferSizes != 0)
							{
								throw new Exception("GET_TARGET_NAME=" + displayConfigBufferSizes);
							}
							Display display = d;
							string text = Marshal.PtrToStringUni(IntPtr.Add(intPtr2, 164), 128);
							char[] trimChars = new char[1];
							display.Device = text.TrimEnd(trimChars);
						}
						finally
						{
							Marshal.FreeHGlobal(intPtr2);
						}
						if (!list.Any((Display x) => x.Key == d.Key))
						{
							list.Add(d);
						}
					}
					return list;
				}
				}
			}
			finally
			{
				Marshal.FreeHGlobal(intPtr);
			}
		}
		throw new Exception("display topology remained unstable");
	}

	public Color Read(Display d)
	{
		if (!Displays().Any((Display x) => x.Key == d.Key))
		{
			throw new Exception("saved display disconnected or identity changed");
		}
		IntPtr intPtr = Packet(d, 15, 36);
		try
		{
			int num = DisplayConfigGetDeviceInfo(intPtr);
			switch (num)
			{
			case 0:
			{
				Color color = new Color();
				color.Modern = true;
				color.Supported = (Marshal.ReadInt32(intPtr, 20) & 0x10) != 0;
				color.On = Marshal.ReadInt32(intPtr, 32) == 2;
				return color;
			}
			default:
				throw new Exception("GET_COLOR_INFO_2=" + num);
			case 50:
			case 87:
				break;
			}
		}
		finally
		{
			Marshal.FreeHGlobal(intPtr);
		}
		intPtr = Packet(d, 9, 32);
		try
		{
			int num2 = DisplayConfigGetDeviceInfo(intPtr);
			if (num2 != 0)
			{
				throw new Exception("GET_COLOR_INFO=" + num2);
			}
			int num3 = Marshal.ReadInt32(intPtr, 20);
			Color color2 = new Color();
			color2.Supported = (num3 & 1) != 0;
			color2.On = (num3 & 2) != 0 && (num3 & 4) == 0;
			return color2;
		}
		finally
		{
			Marshal.FreeHGlobal(intPtr);
		}
	}

	public void Set(Display d, bool on)
	{
		Color color = Read(d);
		if (!color.Supported)
		{
			throw new Exception("HDR unsupported");
		}
		IntPtr intPtr = Packet(d, color.Modern ? 16 : 10, 24);
		try
		{
			Marshal.WriteInt32(intPtr, 20, on ? 1 : 0);
			int num = DisplayConfigSetDeviceInfo(intPtr);
			if (num != 0)
			{
				throw new Exception("DisplayConfigSetDeviceInfo=" + num);
			}
		}
		finally
		{
			Marshal.FreeHGlobal(intPtr);
		}
	}

	public bool Alive(Lease l)
	{
		try
		{
			Process processById = Process.GetProcessById(l.Pid);
			return !processById.HasExited && processById.StartTime.ToUniversalTime().Ticks == l.Birth;
		}
		catch
		{
			return false;
		}
	}

	public bool OtherPlayer(Store s, int caller)
	{
		string[] array = new string[2] { "mpv", "mpvnet" };
		foreach (string processName in array)
		{
			Process[] processesByName = Process.GetProcessesByName(processName);
			foreach (Process p in processesByName)
			{
				if (p.Id != caller && !p.HasExited && !s.Participants.Any((Lease l) => l.Pid == p.Id && Alive(l)))
				{
					return true;
				}
			}
		}
		return false;
	}
}
