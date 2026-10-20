namespace RiftReader2.Application;

/// <summary>
/// Minimal input boundary for one already-selected target. Implementations own target identity checks.
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
