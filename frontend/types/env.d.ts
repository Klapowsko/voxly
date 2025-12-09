/// <reference types="node" />

declare namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_API_URL?: string;
    NEXT_PUBLIC_API_TOKEN?: string;
  }
}

declare var process: {
  env: NodeJS.ProcessEnv;
};

