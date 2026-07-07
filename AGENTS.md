# Kilo Agent Configuration

This file documents agent configurations and workflow practices for this project.

## Available Agents

### fullstack-architect (Global)
A visionary full-stack architect who thinks big and builds ambitious, scalable systems. Specializes in:
- **React frontends**: Component-driven architecture, atomic design, advanced state management, real-time features, and visually stunning modern styling with Tailwind CSS + shadcn/ui
- **Frontend Design & Aesthetics**: Premium, state-of-the-art designs using a custom HSL design-system theme (dark/light modes, glassmorphism, smooth gradients, premium Google Fonts — Inter, Roboto, Outfit), subtle micro-animations/transitions, and Tailwind CSS control
- **Python backends**: Async-first FastAPI, clean architecture, horizontal scaling, observability
- **System thinking**: Always considers scale, integration, extensibility, and long-term maintainability

### code-reviewer
Senior software engineer conducting thorough code reviews (quality, security, performance, maintainability).

### code-simplifier
Expert refactoring specialist for cleaner, more maintainable code.

### test-engineer
QA specialist for comprehensive tests and improved code coverage.

## Project-Specific Guidelines

- Python code follows existing patterns in `src/` directory
- Async-first design with proper error handling and retry logic
- Weaviate integration with embedded vectors for server-side permission issues
- Thread-safe model initialization with locks for concurrent access
- Take charge of creating and using the terminal directly using tools when required, without instructing the user to run those commands.
- If user permission is needed, only ask for permission directly without providing details or step-by-step instructions on how the user can execute it manually unless explicitly asked.