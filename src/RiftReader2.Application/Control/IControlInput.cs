namespace RiftReader2.Application;

/// <summary>
/// Minimal input boundary for one already-selected target. Implementations own target identity checks.
/// IsTargetCurrent may run concurrently with release and must not hold an input lock.
/// Down/move methods run inside the deadline injection gate: no heavyweight inspection,
/// waits or file I/O. Up methods must never depend on identity, foreground or arm validity.
/// </summary>
public interface IControlInput
{
    bool IsTargetCurrent();

    void KeyDown(string key);

    void KeyUp(string key);

    void ButtonDown(string button);

    void ButtonUp(string button);

    void MoveRelative(int deltaX, int deltaY);

    void Wheel(int notches);
}
