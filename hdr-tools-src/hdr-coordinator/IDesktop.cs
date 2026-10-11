public interface IDesktop
{
	Color Read(Display d);

	void Set(Display d, bool on);

	bool Alive(Lease l);

	bool OtherPlayer(Store s, int caller);
}
