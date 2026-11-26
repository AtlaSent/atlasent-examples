# Explain a refund decision on your computer

Run a small language model on your own computer to explain a fictional refund hold. You supply the recorded decision and the model drafts a message for the operator. This example only generates text. It has no connection to a payment processor or an AtlaSent tenant.

## Run your first example

1. [Download Ollama](https://ollama.com/download), install it, and open it.
2. Open **PowerShell** on Windows or **Terminal** on macOS or Linux. Paste the whole line below and press Enter.

```sh
ollama run qwen3:4b "Explain the recorded decision in one sentence. Refund USD 72. Decision HOLD. Refunds of USD 50 or more require manager approval. Next step: send to finance manager for review. /no_think"
```

The first run downloads [Qwen3 4B](https://ollama.com/library/qwen3:4b), about 2.5 GB. After that, you can rerun the command offline. On a CPU, allow a minute or more for the first answer. Local generation uses your computer's memory and electricity and incurs no hosted-model token charges.

**Check your result.** Wording can vary. The answer should say the USD 72 refund is on hold because it exceeds the USD 50 approval threshold and direct the operator to the finance manager. If it says the refund was approved, issued, or sent for review, it added an event that never occurred.

If your terminal cannot find `ollama`, reopen the terminal after installation. If it cannot connect to Ollama, open the app, or start `ollama serve` in a second terminal on Linux. To check where the model ran, enter `ollama ps` shortly after the response and look for `qwen3:4b` and its CPU or GPU allocation.

## Save your own assistant (optional)

Run `ollama run qwen3:4b` with no prompt. At the `>>>` prompt, enter each line separately.

```text
/set system Explain recorded refund decisions to finance operators in two sentences. Use only the supplied facts. Give the decision, reason, and next step. When a field is missing, say it was not recorded. Never invent an approval or an action.
/save atlasent-assistant
/bye
```

Open it again with `ollama run atlasent-assistant`. Try this second record:

```text
Refund amount USD 72. Decision HOLD. Reason: manager approval pending.
```

The answer should preserve the hold and say the next step was not recorded. Saving this assistant reuses your instructions with the downloaded model. You can review its answers directly against the records you provide.

For a separate example of using a verified permit before a real action runs, see the [deployment gate walkthrough](../github-action-deploy/).
