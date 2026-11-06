using System.Text.RegularExpressions;

namespace RiftReader2.Tests;

public sealed class DiscoveryExplorerStaticTests
{
    [Fact]
    public void ExplorerIsSelfContainedUsesSafeDomAndSupportsLocalDownloads()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "Fixtures", "discovery_explorer.html");
        var html = File.ReadAllText(path);
        Assert.Contains("discovery-compilation/1", html, StringComparison.Ordinal);
        Assert.Contains("type=\"file\"", html, StringComparison.Ordinal);
        Assert.Contains("new Blob(", html, StringComparison.Ordinal);
        Assert.Contains("URL.createObjectURL", html, StringComparison.Ordinal);
        Assert.Contains("textContent", html, StringComparison.Ordinal);
        Assert.Contains("pageSize = 100", html, StringComparison.Ordinal);
        Assert.Contains("filtered.slice(page*pageSize", html, StringComparison.Ordinal);
        Assert.Contains("selectedRecords:filtered.length", html, StringComparison.Ordinal);
        Assert.Contains("row.evidenceSha256,row.sourceId,row.sourcePath", html, StringComparison.Ordinal);
        Assert.Contains("utcSortKey", html, StringComparison.Ordinal);
        Assert.Contains("aria-sort", html, StringComparison.Ordinal);
        Assert.DoesNotContain("fetch(", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("XMLHttpRequest", html, StringComparison.Ordinal);
        Assert.DoesNotContain("innerHTML", html, StringComparison.Ordinal);
        Assert.DoesNotContain("<script src=", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("<iframe", html, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("connect-src 'none'", html, StringComparison.Ordinal);

        var ids = Regex.Matches(html, "\\bid=\"([^\"]+)\"")
            .Select(match => match.Groups[1].Value).ToArray();
        Assert.NotEmpty(ids);
        Assert.Equal(ids.Length, ids.Distinct(StringComparer.Ordinal).Count());
        foreach (var required in new[] { "file", "search", "source", "category", "status",
                     "rows", "detail", "csv", "json", "prev", "next", "visibleCount" })
            Assert.Contains(required, ids);
    }
}
