import uvicorn


def main():
    uvicorn.run(
        "voicetype.app:app",
        host="0.0.0.0",
        port=8000,
        # reload=args.test,
    )

if __name__ == "__main__":
    main()
