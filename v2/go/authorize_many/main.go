package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/atlasent-systems-inc/atlasent-sdk-go/atlasent"
	"github.com/google/uuid"
)

func main() {
	client := atlasent.New(atlasent.ClientOptions{
		APIURL: os.Getenv("ATLASENT_API_URL"),
		APIKey: os.Getenv("ATLASENT_API_KEY"),
	})

	actor := atlasent.Actor{ID: "agent-001", Type: "agent"}
	actions := []string{"tool:web_search", "tool:code_execute", "data:read", "data:write", "model:invoke"}
	payloads := make([]atlasent.EvaluationPayload, len(actions))
	for i, a := range actions {
		payloads[i] = atlasent.EvaluationPayload{
			Actor:  actor,
			Action: atlasent.Action{ID: uuid.NewString(), Type: a},
			Target: atlasent.Target{ID: "res", Type: "resource"},
		}
	}

	results := client.AuthorizeMany(context.Background(), payloads)
	fmt.Printf("%-25s %-20s %s\n", "Action", "Decision", "Risk")
	fmt.Println("─────────────────────────────────────────────────────")
	for _, r := range results {
		if r.Err != nil {
			log.Printf("%-25s ERROR: %v", r.Payload.Action.Type, r.Err)
			continue
		}
		fmt.Printf("%-25s %-20s %s (%d)\n", r.Payload.Action.Type, r.Result.Decision, r.Result.Risk.Level, r.Result.Risk.Score)
	}
}
