# Dataset Service

## Purpose

The Dataset Service is responsible for dataset ingestion, validation, versioning, storage, metadata management, and dataset lineage tracking.

The goal is to ensure all training jobs use reproducible and validated datasets.

---

# Responsibilities

* Dataset Upload
* Dataset Validation
* Dataset Versioning
* Dataset Storage
* Metadata Extraction
* Dataset Statistics
* Dataset Lineage Tracking

---

# Supported Formats

## CSV

```csv
instruction,response
"What is AI?","Artificial Intelligence..."
```

## JSON

```json
[
  {
    "instruction":"What is AI?",
    "response":"Artificial Intelligence"
  }
]
```

## JSONL

```json
{"instruction":"What is AI?","response":"Artificial Intelligence"}
{"instruction":"What is ML?","response":"Machine Learning"}
```

---

# Dataset Types

## Instruction Tuning

```json
{
  "instruction":"",
  "input":"",
  "output":""
}
```

---

## Chat Dataset

```json
{
  "messages":[
    {"role":"user","content":"Hello"},
    {"role":"assistant","content":"Hi"}
  ]
}
```

---

## Q&A Dataset

```json
{
  "question":"",
  "answer":""
}
```

---

# Upload Workflow

```text
User Upload
      ↓
Temporary Storage
      ↓
Schema Detection
      ↓
Validation
      ↓
Statistics Generation
      ↓
Version Creation
      ↓
MinIO Storage
      ↓
Metadata Persistence
```

---

# Dataset Validation

## Schema Validation

Checks:

* Required Columns
* Data Types
* Empty Records

---

## Duplicate Detection

Methods:

* Exact Match
* Hash Comparison

Example:

```text
SHA256(record)
```

---

## Missing Data Validation

Reject:

* Empty prompts
* Empty responses
* Null values

---

## Length Validation

Check:

* Minimum Tokens
* Maximum Tokens

Example:

```text
Prompt Length < 4096

Response Length < 4096
```

---

# Toxicity Validation

Future Feature

Detect:

* Hate Speech
* Toxic Content
* Personally Identifiable Information

---

# Dataset Statistics

Generated Automatically

## Statistics

```json
{
  "records":12000,
  "avg_prompt_length":56,
  "avg_response_length":121,
  "duplicates":23
}
```

---

# Versioning Strategy

Every upload creates a version.

Example:

```text
customer-support
├── v1
├── v2
├── v3
```

---

# Metadata Model

```json
{
  "dataset_id":"uuid",
  "version":"v3",
  "records":12000,
  "size_mb":45,
  "created_by":"user_id"
}
```

---

# Storage Strategy

## MinIO Structure

```text
datasets/

    customer-support/

        v1/

        v2/

        v3/
```

---

# Dataset Lineage

Track:

```text
Dataset
    ↓
Version
    ↓
Training Job
    ↓
Model
```

Purpose:

Full reproducibility.

---

# Dataset APIs

## Upload Dataset

```http
POST /datasets
```

---

## Upload Version

```http
POST /datasets/{id}/versions
```

---

## Dataset Statistics

```http
GET /datasets/{id}/statistics
```

---

## Dataset Versions

```http
GET /datasets/{id}/versions
```

---

# Failure States

## Validation Failed

```json
{
  "status":"failed",
  "reason":"missing_response_column"
}
```

## Corrupted File

```json
{
  "status":"failed",
  "reason":"invalid_json"
}
```

---

# Design Goals

* Reproducible
* Version Controlled
* Storage Efficient
* Training Ready
* Scalable
