// go-http-middleware demonstrates protecting HTTP endpoints with the AtlaSent
// Go SDK Middleware. On allow the Permit is available in the request context.
// On deny, the middleware writes 403 JSON automatically.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"

	atlasent "github.com/atlasent-systems-inc/atlasent-sdk/go/v2"
)

func main() {
	client := atlasent.New(atlasent.Options{
		APIKey: os.Getenv("ATLASENT_API_KEY"),
	})

	mux := http.NewServeMux()
	mux.HandleFunc("/api/deploy", deployHandler)
	mux.HandleFunc("/api/data-export", dataExportHandler)

	// Wrap with AtlaSent middleware. Reads action from X-AtlaSent-Action header
	// and subject from X-AtlaSent-Subject header.
	protected := client.Middleware(&atlasent.MiddlewareOptions{
		OnDeny: func(r *http.Request, err *atlasent.DeniedError) {
			log.Printf("denied: action=%s reason=%s eval_id=%s",
				r.Header.Get("X-AtlaSent-Action"), err.Reason, err.EvaluationID)
		},
	})(mux)

	addr := ":8080"
	fmt.Printf("listening on %s\n", addr)
	log.Fatal(http.ListenAndServe(addr, protected))
}

func deployHandler(w http.ResponseWriter, r *http.Request) {
	permit := r.Context().Value(atlasent.PermitContextKey).(*atlasent.Permit)
	json.NewEncoder(w).Encode(map[string]any{
		"status":    "deployed",
		"permit_id": permit.PermitID,
	})
}

func dataExportHandler(w http.ResponseWriter, r *http.Request) {
	permit := r.Context().Value(atlasent.PermitContextKey).(*atlasent.Permit)
	json.NewEncoder(w).Encode(map[string]any{
		"export_url": "https://storage.example.com/export-123.csv",
		"permit_id":  permit.PermitID,
	})
}
