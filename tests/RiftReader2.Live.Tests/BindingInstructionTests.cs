namespace RiftReader2.Live.Tests;

public sealed class BindingInstructionTests
{
    private const string Nonce = "0123456789abcdef0123456789abcdef";

    [Fact]
    public void EveryAttachmentConditionallyExplainsPriorBindingRecovery()
    {
        var instructions = Program.BindingInstructions(Nonce);

        Assert.Equal(new[]
        {
            "============================================================",
            "If this addon load is already bound to another reader, enter /reloadui and wait for it to finish first.",
            "Then enter this command locally in RIFT chat:",
            $"/rr2bind {Nonce}",
            "This challenge is valid only for this reader attachment.",
            "============================================================"
        }, instructions);
        Assert.Equal(1, instructions.Count(line => line == $"/rr2bind {Nonce}"));
    }
}
