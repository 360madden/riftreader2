using RiftReader2.Cli;

using var cancellation = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    cancellation.Cancel();
};
return await CliRunner.RunAsync(args, Console.Out, Console.Error, cancellation.Token);
