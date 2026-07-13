const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function uploadFiles(files) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    const response = await fetch(`${BASE_URL}/ingest/upload`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || 'Upload failed');
    }

    return response.json();
}

export async function listDocuments() {
    const response = await fetch(`${BASE_URL}/ingest/documents`);
    if (!response.ok) {
        throw new Error('Failed to list documents');
    }
    return response.json();
}

export async function deleteDocument(docId) {
    const response = await fetch(`${BASE_URL}/ingest/documents/${docId}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        throw new Error('Failed to delete document');
    }
    return response.json();
}

export async function replaceDocument(docId, file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${BASE_URL}/ingest/documents/${docId}`, {
        method: 'PUT',
        body: formData,
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to replace document');
    }

    return response.json();
}

export async function ingestUrl(url) {
    const response = await fetch(`${BASE_URL}/ingest/url`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to ingest URL');
    }
    return response.json();
}

export async function sendQuery(query, messages = [], topK = 5, forcedStrategy = null) {
    const body = {
        query,
        messages,
        top_k: topK,
    };
    if (forcedStrategy) {
        body.forced_strategy = forcedStrategy;
    }

    const response = await fetch(`${BASE_URL}/query`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || 'Query failed');
    }

    return response.json();
}
