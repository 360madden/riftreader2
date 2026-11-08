namespace RiftReader2.Live;

/// <summary>
/// Computes only the current-build intern bucket candidate for bounded C-string
/// bytes. It does not look up an object or establish ownership or freshness.
/// </summary>
internal static class CurrentBuildOpaqueInternBucketCandidate
{
    internal const int BucketCount = 513;
    internal const int BucketStride = 24;
    internal const int MaximumAllowedLength = 4096;

    // maxLength is the maximum payload length, excluding the required terminator.
    internal static bool TryGetBucket(ReadOnlySpan<byte> bytes, int maxLength, out int bucket)
    {
        bucket = 0;
        if (maxLength < 0 || maxLength > MaximumAllowedLength) return false;
        uint hash = 0;
        int limit = Math.Min(bytes.Length, maxLength + 1);
        for (int index = 0; index < limit; index++)
        {
            byte value = bytes[index];
            if (value == 0)
            {
                bucket = (int)(hash % BucketCount);
                return true;
            }
            if (index == maxLength) return false;
            hash = unchecked(hash * 33 + (uint)(int)(sbyte)value);
        }
        return false;
    }
}
