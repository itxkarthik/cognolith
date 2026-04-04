"use client";

import { useEffect, useMemo, useRef, useState } from "react";

interface UseAutoSaveOptions<T> {
	value: T;
	onSave: (value: T) => Promise<void> | void;
	enabled?: boolean;
	delayMs?: number;
	skipInitial?: boolean;
	serialize?: (value: T) => string;
}

interface UseAutoSaveResult {
	isSaving: boolean;
	lastSavedAt: Date | null;
	error: string | null;
}

export function useAutoSave<T>({
	value,
	onSave,
	enabled = true,
	delayMs = 900,
	skipInitial = true,
	serialize,
}: UseAutoSaveOptions<T>): UseAutoSaveResult {
	const [isSaving, setIsSaving] = useState(false);
	const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
	const [error, setError] = useState<string | null>(null);

	const initializedRef = useRef(false);
	const lastSavedSnapshotRef = useRef<string | null>(null);

	const snapshot = useMemo(() => {
		if (serialize) {
			return serialize(value);
		}

		try {
			return JSON.stringify(value);
		} catch {
			return String(value);
		}
	}, [serialize, value]);

	useEffect(() => {
		if (!enabled) {
			return;
		}

		if (!initializedRef.current) {
			initializedRef.current = true;
			if (skipInitial) {
				lastSavedSnapshotRef.current = snapshot;
				return;
			}
		}

		if (lastSavedSnapshotRef.current === snapshot) {
			return;
		}

		const timeoutId = window.setTimeout(async () => {
			setIsSaving(true);
			setError(null);
			try {
				await onSave(value);
				lastSavedSnapshotRef.current = snapshot;
				setLastSavedAt(new Date());
			} catch (saveError) {
				setError(
					saveError instanceof Error ? saveError.message : "Auto-save failed."
				);
			} finally {
				setIsSaving(false);
			}
		}, delayMs);

		return () => {
			window.clearTimeout(timeoutId);
		};
	}, [delayMs, enabled, onSave, skipInitial, snapshot, value]);

	return {
		isSaving,
		lastSavedAt,
		error,
	};
}
