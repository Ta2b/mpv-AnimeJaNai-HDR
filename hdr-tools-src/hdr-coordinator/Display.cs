public class Display
{
	public uint Low;

	public uint Id;

	public int High;

	public string Device;

	public string Key => High + ":" + Low + ":" + Id + ":" + Device;
}
