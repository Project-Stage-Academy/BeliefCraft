import weaviate  # type: ignore

with weaviate.connect_to_local() as client:
    result = client.backup.restore(
        backup_id="backup_for_sharing",
        backend="filesystem",
        wait_for_completion=True,
        roles_restore="all",
        users_restore="all",
    )

print(result)
