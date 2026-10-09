# Corpus frontend

The frontend is a React and TypeScript application built with Vite. This guide
shows you how to run it on a development machine.

## Prerequisites

* Node.js 22
* The backend running on `http://127.0.0.1:8000`. See the
  [backend guide](../backend/README.md).

## Running the frontend

1. Install the dependencies:

   ```sh
   cd frontend
   npm install
   ```

2. Start the development server:

   ```sh
   npm run dev
   ```

Open `http://localhost:5173`. The development server forwards `/api` requests
and WebSockets to the backend. The interface language follows `APP_LANGUAGE`
in `backend/.env`; with several `APP_LANGUAGES`, users switch in the header.
Restart the development server after changing them.

## Checking your changes

| Command | What it does |
|---|---|
| `npm test` | Runs the tests (Vitest and Testing Library) |
| `npm run lint` | Runs Oxlint |
| `npm run build` | Type-checks and builds the production bundle |

## Customizing the interface

Add pages, sidebar links, translations and themes in `src/custom/` without
editing core files. See [Customizing Corpus](../documentations/customization/en.md).
