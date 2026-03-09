package handler

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"

	"github.com/gin-gonic/gin"
)

// ProxyHandler forwards /api/v1/* requests to the appropriate backend service.
// Upload routes are handled by UploadHandler before reaching here.
type ProxyHandler struct {
	datasetProxy *httputil.ReverseProxy
	taskProxy    *httputil.ReverseProxy
}

func NewProxyHandler(datasetServiceURL, taskServiceURL string) (*ProxyHandler, error) {
	dURL, err := url.Parse(datasetServiceURL)
	if err != nil {
		return nil, err
	}
	tURL, err := url.Parse(taskServiceURL)
	if err != nil {
		return nil, err
	}
	return &ProxyHandler{
		datasetProxy: httputil.NewSingleHostReverseProxy(dURL),
		taskProxy:    httputil.NewSingleHostReverseProxy(tURL),
	}, nil
}

// taskServicePrefixes are the path prefixes routed to task-service.
var taskServicePrefixes = []string{
	"/api/v1/tasks",
	"/api/v1/users",
	"/api/v1/webhooks",
}

// Handle routes the request to dataset-service or task-service based on path prefix.
// Only proxies /api/v1/* paths; everything else returns 404.
func (h *ProxyHandler) Handle(c *gin.Context) {
	path := c.Request.URL.Path
	if !strings.HasPrefix(path, "/api/v1/") {
		c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
		return
	}
	for _, prefix := range taskServicePrefixes {
		if strings.HasPrefix(path, prefix) {
			h.taskProxy.ServeHTTP(c.Writer, c.Request)
			return
		}
	}
	h.datasetProxy.ServeHTTP(c.Writer, c.Request)
}
