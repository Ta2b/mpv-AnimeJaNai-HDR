using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Principal;
using System.Threading;
using System.Web.Script.Serialization;

public class Program
{
	private static JavaScriptSerializer json = new JavaScriptSerializer();

	public static int Main(string[] args)
	{
		try
		{
			WindowsDesktop desktop = new WindowsDesktop();
			if (args.Length == 1 && args[0] == "inspect")
			{
				Console.WriteLine(json.Serialize((object)(from d in WindowsDesktop.Displays()
					select new
					{
						display = d,
						color = desktop.Read(d)
					})));
				return 0;
			}
			if (args.Length < 3)
			{
				throw new Exception("usage: acquire PID TOKEN UID enable|follow MAX | release PID TOKEN | inspect");
			}
			string text = args[0];
			int pid = int.Parse(args[1]);
			string token = args[2];
			Process processById = Process.GetProcessById(pid);
			string text2 = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AnimeJaNaiHDR", "session-" + processById.SessionId);
			Directory.CreateDirectory(text2);
			string text3 = Path.Combine(text2, "leases-v1.json");
			string value = WindowsIdentity.GetCurrent().User.Value;
			using (Mutex mutex = new Mutex(initiallyOwned: false, "Local\\AnimeJaNaiHDR-v1-" + value))
			{
				bool flag = false;
				try
				{
					try
					{
						flag = mutex.WaitOne(4000);
					}
					catch (AbandonedMutexException)
					{
						flag = true;
					}
					if (!flag)
					{
						throw new Exception("coordinator-lock-timeout");
					}
					Store store = (File.Exists(text3) ? json.Deserialize<Store>(File.ReadAllText(text3)) : new Store());
					Coordinator coordinator = new Coordinator(desktop);
					object obj;
					if (text == "release")
					{
						store.Leases.RemoveAll((Lease l) => l.Pid == pid && (token == "all" || l.Token == token));
						string text4 = coordinator.Cleanup(store, pid);
						for (int num = 0; num < 2; num++)
						{
							if (!(text4 == "restore-awaiting-off") && !text4.StartsWith("restore-command-error:") && !text4.StartsWith("restore-deferred:"))
							{
								break;
							}
							Thread.Sleep(200);
							text4 = coordinator.Cleanup(store, pid);
						}
						obj = new
						{
							state = "released",
							reason = text4
						};
					}
					else
					{
						if (!(text == "acquire") || args.Length != 6)
						{
							throw new Exception("invalid coordinator command");
						}
						uint uid = uint.Parse(args[3]);
						List<Display> list = (from d in WindowsDesktop.Displays()
							where d.Id == uid
							select d).ToList();
						if (list.Count != 1)
						{
							throw new Exception("plugin uid absent or ambiguous across adapters");
						}
						Lease lease = new Lease();
						lease.Pid = pid;
						lease.Token = token;
						lease.Birth = processById.StartTime.ToUniversalTime().Ticks;
						Lease lease2 = lease;
						obj = coordinator.Update(store, lease2, list[0], args[4] == "enable", Math.Max(1, Math.Min(5, int.Parse(args[5]))), DateTime.UtcNow.Ticks);
					}
					string text5 = text3 + ".tmp";
					File.WriteAllText(text5, json.Serialize((object)store));
					if (File.Exists(text3))
					{
						File.Replace(text5, text3, null);
					}
					else
					{
						File.Move(text5, text3);
					}
					Console.WriteLine(json.Serialize(obj));
				}
				finally
				{
					if (flag)
					{
						mutex.ReleaseMutex();
					}
				}
			}
			return 0;
		}
		catch (Exception ex2)
		{
			Console.WriteLine(json.Serialize((object)new
			{
				state = "error",
				reason = ex2.Message
			}));
			return 1;
		}
	}

	static Program()
	{
		//IL_0000: Unknown result type (might be due to invalid IL or missing references)
		//IL_000a: Expected Obj, but got Unknown
	}
}
