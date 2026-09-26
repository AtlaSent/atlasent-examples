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

	result, err := client.Evaluate(context.Background(), atlasent.EvaluationPayload{
		Actor:  atlasent.Actor{ID: "user-123", Type: "user"},
		Action: atlasent.Action{ID: uuid.NewString(), Type: "data.export"},
		Target: atlasent.Target{ID: "dataset-456", Type: "dataset", Sensitivity: "confidential", Environment: "production"},
	})
	if err != nil {
		log.Fatalf("evaluate: %v", err)
	}

	fmt.Printf("Decision:   %s\n", result.Decision)
	fmt.Printf("Risk Level: %s (score: %d/100)\n", result.Risk.Level, result.Risk.Score)
	if result.PermitID != "" {
		fmt.Printf("Permit ID:  %s\n", result.PermitID)
	}
}
