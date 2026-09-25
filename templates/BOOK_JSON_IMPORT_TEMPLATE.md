# Reusable Book JSON template

Use `book-import-template.json` as a starting point for a Book JSON import.

- Keep `book.id` in the form `book1`, `book2`, `book3`, and so on.
- Scene IDs and choice IDs may use letters, numbers, hyphens, and underscores.
- Every `nextSceneId` must match a scene `id` in the same file.
- Leave the final scene's `choices` array empty to create a proper ending.
- Upload the saved `.json` file through **Story Admin → Import Book JSON**. It
  creates a private draft only; it never publishes directly to players.
