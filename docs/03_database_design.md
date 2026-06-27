````md
# Database Design

## Database Technology

**PostgreSQL**

### Reasons

- ACID Compliance
- Strong Relationship Support
- Easy Analytics and Reporting
- Production-Proven Reliability
- Excellent Scalability and Performance

---

# Entity Relationship Diagram

```text
User
 ├── Dataset
 │     └── DatasetVersion
 │
 ├── TrainingJob
 │     └── Experiment
 │
 ├── Model
 │     └── ModelVersion
 │
 └── Deployment
```

---

# Users Table

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Stores user account information and authentication details.

---

# Datasets Table

```sql
CREATE TABLE datasets (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Stores dataset metadata uploaded by users.

---

# Dataset Versions Table

```sql
CREATE TABLE dataset_versions (
    id UUID PRIMARY KEY,
    dataset_id UUID REFERENCES datasets(id),
    version VARCHAR(50),
    file_path TEXT,
    record_count INTEGER,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Tracks different versions of datasets and their validation status.

---

# Training Jobs Table

```sql
CREATE TABLE training_jobs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    dataset_version_id UUID,
    model_name VARCHAR(255),
    method VARCHAR(50),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Stores fine-tuning and training job configurations.

---

# Experiments Table

```sql
CREATE TABLE experiments (
    id UUID PRIMARY KEY,
    training_job_id UUID,
    mlflow_run_id VARCHAR(255),
    loss FLOAT,
    learning_rate FLOAT,
    gpu_memory FLOAT,
    training_time INTEGER
);
```

### Purpose

Stores experiment tracking metrics generated during training.

---

# Models Table

```sql
CREATE TABLE models (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    name VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Stores registered models in the model registry.

---

# Model Versions Table

```sql
CREATE TABLE model_versions (
    id UUID PRIMARY KEY,
    model_id UUID REFERENCES models(id),
    version VARCHAR(50),
    artifact_path TEXT,
    stage VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Tracks model versions and lifecycle stages.

---

# Evaluations Table

```sql
CREATE TABLE evaluations (
    id UUID PRIMARY KEY,
    model_version_id UUID,
    rouge FLOAT,
    bertscore FLOAT,
    semantic_similarity FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Stores evaluation metrics for trained models.

---

# Deployments Table

```sql
CREATE TABLE deployments (
    id UUID PRIMARY KEY,
    model_version_id UUID,
    endpoint_url TEXT,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Purpose

Stores deployment information and endpoint details.

---

# Future Tables

The following tables can be added in future releases:

- `audit_logs`
- `api_keys`
- `organizations`
- `teams`
- `billing`
- `usage_metrics`

---

# Database Index Recommendations

```sql
CREATE INDEX idx_users_email ON users(email);

CREATE INDEX idx_datasets_user_id
ON datasets(user_id);

CREATE INDEX idx_training_jobs_user_id
ON training_jobs(user_id);

CREATE INDEX idx_model_versions_model_id
ON model_versions(model_id);

CREATE INDEX idx_deployments_model_version_id
ON deployments(model_version_id);
```

---

# Database Scalability Considerations

- Use UUIDs for distributed systems.
- Store large artifacts in object storage (MinIO/S3) instead of PostgreSQL.
- Add table partitioning for large experiment datasets.
- Use read replicas for analytics workloads.
- Implement caching using Redis for frequently accessed data.

---

# Summary

This database schema supports:

- User Management
- Dataset Versioning
- Training Job Tracking
- Experiment Tracking
- Model Registry
- Evaluation Management
- Model Deployment
- Future Enterprise Features
````
