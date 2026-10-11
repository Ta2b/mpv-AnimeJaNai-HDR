using System;
using System.Collections.Generic;
using System.Linq;

public class Coordinator
{
	private readonly IDesktop desktop;

	public Coordinator(IDesktop d)
	{
		desktop = d;
	}

	public string Cleanup(Store s, int caller)
	{
		s.Leases.RemoveAll((Lease l) => !desktop.Alive(l));
		s.Participants.RemoveAll((Lease l) => !desktop.Alive(l));
		string result = "released";
		Screen[] array = s.Screens.ToArray();
		foreach (Screen screen in array)
		{
			List<Lease> leases = s.Leases;
			Func<Lease, bool> predicate = (Lease l) => l.Key == screen.Display.Key;
			if (leases.Any(predicate))
			{
				continue;
			}
			Color color;
			try
			{
				color = desktop.Read(screen.Display);
			}
			catch (Exception ex)
			{
				result = "restore-deferred: " + ex.Message;
				continue;
			}
			if (screen.Pending && color.On)
			{
				screen.Owned = true;
				screen.Pending = false;
			}
			if ((screen.Owned && color.On) || screen.Pending)
			{
				if (desktop.OtherPlayer(s, caller))
				{
					result = "restore-deferred-other-player";
					continue;
				}
				if (screen.RestoreAttempts >= 3)
				{
					result = "restore-budget-exhausted";
					continue;
				}
				screen.RestoreAttempts++;
				try
				{
					desktop.Set(screen.Display, on: false);
					if (desktop.Read(screen.Display).On)
					{
						result = "restore-awaiting-off";
						continue;
					}
				}
				catch (Exception ex2)
				{
					result = "restore-command-error: " + ex2.Message;
					continue;
				}
				screen.Pending = false;
				result = "restored-off";
			}
			if (screen.Pending)
			{
				if (DateTime.UtcNow.Ticks - screen.LastRequest < 150000000)
				{
					result = "awaiting-late-on";
					continue;
				}
				screen.Pending = false;
			}
			s.Screens.Remove(screen);
		}
		return result;
	}

	public object Update(Store s, Lease lease, Display display, bool enable, int maxAttempts, long now)
	{
		s.Leases.RemoveAll((Lease l) => l.Pid == lease.Pid || !desktop.Alive(l));
		lease.Key = display.Key;
		s.Leases.Add(lease);
		s.Participants.RemoveAll((Lease l) => l.Pid == lease.Pid || !desktop.Alive(l));
		s.Participants.Add(lease);
		Cleanup(s, lease.Pid);
		Screen screen = s.Screens.Find((Screen x) => x.Display.Key == display.Key);
		if (screen == null)
		{
			Screen screen2 = new Screen();
			screen2.Display = display;
			screen = screen2;
			s.Screens.Add(screen);
		}
		screen.RestoreAttempts = 0;
		Color color = desktop.Read(display);
		string reason = "follow";
		if (screen.Pending && color.On)
		{
			screen.Pending = false;
			screen.Owned = true;
		}
		if (screen.Owned && !color.On)
		{
			screen.Owned = false;
			screen.Inhibited = true;
			reason = "manual-off-respected";
		}
		if (!color.Supported)
		{
			reason = "unsupported";
		}
		else if (color.On)
		{
			reason = "on-confirmed";
		}
		else if (screen.Inhibited)
		{
			reason = "manual-off-respected";
		}
		else if (enable)
		{
			if (screen.Attempts >= maxAttempts)
			{
				reason = "attempt-budget-exhausted";
			}
			else if (now - screen.LastRequest < 20000000)
			{
				reason = "awaiting-confirmation";
			}
			else
			{
				screen.Attempts++;
				screen.LastRequest = now;
				try
				{
					desktop.Set(display, on: true);
					screen.Pending = true;
					color = desktop.Read(display);
					if (color.On)
					{
						screen.Owned = true;
						screen.Pending = false;
						reason = "on-confirmed";
					}
					else
					{
						reason = "awaiting-confirmation";
					}
				}
				catch (Exception ex)
				{
					reason = "command-error: " + ex.Message;
				}
			}
		}
		return new
		{
			state = (color.On ? "on" : "off"),
			supported = color.Supported,
			owned = screen.Owned,
			attempts = screen.Attempts,
			reason = reason,
			key = display.Key
		};
	}
}
