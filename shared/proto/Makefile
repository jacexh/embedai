.PHONY: gen gen-go gen-python

PROTO_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON_OUT := $(PROTO_DIR)../python_proto

gen: gen-go gen-python

gen-go:
	protoc --go_out=. --go-grpc_out=. *.proto

gen-python:
	python -m grpc_tools.protoc -I. \
		--python_out=$(PYTHON_OUT) \
		--grpc_python_out=$(PYTHON_OUT) \
		*.proto
