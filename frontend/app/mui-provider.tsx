"use client";

import { ReactNode } from "react";
import { AppRouterCacheProvider } from "@mui/material-nextjs/v14-appRouter";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { 
      main: "#616161",
      light: "#8e8e8e",
      dark: "#424242",
    },
    secondary: { 
      main: "#757575",
      light: "#9e9e9e",
      dark: "#616161",
    },
    background: { 
      default: "transparent",
      paper: "rgba(255, 255, 255, 0.2)",
    },
    text: {
      primary: "rgba(0, 0, 0, 0.87)",
      secondary: "rgba(0, 0, 0, 0.6)",
    },
  },
  shape: {
    borderRadius: 16,
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          background: "rgba(255, 255, 255, 0.15)",
          backdropFilter: "blur(40px) saturate(200%)",
          WebkitBackdropFilter: "blur(40px) saturate(200%)",
          border: "1px solid rgba(255, 255, 255, 0.5)",
          borderTop: "1px solid rgba(255, 255, 255, 0.7)",
          boxShadow: `
            0 8px 32px 0 rgba(0, 0, 0, 0.12),
            inset 0 1px 0 0 rgba(255, 255, 255, 0.6),
            0 1px 2px 0 rgba(0, 0, 0, 0.05)
          `,
          borderRadius: 20,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          background: "rgba(255, 255, 255, 0.12)",
          backdropFilter: "blur(30px) saturate(200%)",
          WebkitBackdropFilter: "blur(30px) saturate(200%)",
          border: "1px solid rgba(255, 255, 255, 0.4)",
          borderTop: "1px solid rgba(255, 255, 255, 0.6)",
          boxShadow: `
            0 4px 20px 0 rgba(0, 0, 0, 0.1),
            inset 0 1px 0 0 rgba(255, 255, 255, 0.5)
          `,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 600,
          borderRadius: 12,
          "&.MuiButton-contained": {
            background: "rgba(97, 97, 97, 0.7)",
            backdropFilter: "blur(20px) saturate(180%)",
            WebkitBackdropFilter: "blur(20px) saturate(180%)",
            border: "1px solid rgba(255, 255, 255, 0.3)",
            color: "white",
            boxShadow: "0 2px 8px 0 rgba(0, 0, 0, 0.15), inset 0 1px 0 0 rgba(255, 255, 255, 0.2)",
            "&:hover": {
              background: "rgba(97, 97, 97, 0.85)",
              boxShadow: "0 4px 12px 0 rgba(0, 0, 0, 0.2), inset 0 1px 0 0 rgba(255, 255, 255, 0.3)",
            },
          },
          "&.MuiButton-outlined": {
            borderColor: "rgba(255, 255, 255, 0.4)",
            color: "rgba(0, 0, 0, 0.87)",
            background: "rgba(255, 255, 255, 0.1)",
            backdropFilter: "blur(15px)",
            WebkitBackdropFilter: "blur(15px)",
            "&:hover": {
              borderColor: "rgba(255, 255, 255, 0.6)",
              background: "rgba(255, 255, 255, 0.2)",
            },
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          background: "rgba(255, 255, 255, 0.25)",
          backdropFilter: "blur(20px) saturate(180%)",
          WebkitBackdropFilter: "blur(20px) saturate(180%)",
          border: "1px solid rgba(255, 255, 255, 0.5)",
          borderTop: "1px solid rgba(255, 255, 255, 0.7)",
          boxShadow: "0 2px 8px 0 rgba(0, 0, 0, 0.1), inset 0 1px 0 0 rgba(255, 255, 255, 0.4)",
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: "rgba(255, 255, 255, 0.12)",
          backdropFilter: "blur(35px) saturate(200%)",
          WebkitBackdropFilter: "blur(35px) saturate(200%)",
          borderBottom: "1px solid rgba(255, 255, 255, 0.4)",
          boxShadow: "0 1px 8px 0 rgba(0, 0, 0, 0.08)",
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          background: "rgba(255, 255, 255, 0.2)",
          backdropFilter: "blur(50px) saturate(200%)",
          WebkitBackdropFilter: "blur(50px) saturate(200%)",
          border: "1px solid rgba(255, 255, 255, 0.5)",
          borderTop: "1px solid rgba(255, 255, 255, 0.7)",
          boxShadow: `
            0 12px 48px 0 rgba(0, 0, 0, 0.2),
            inset 0 1px 0 0 rgba(255, 255, 255, 0.6)
          `,
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 8,
          borderRadius: 10,
          background: "rgba(255, 255, 255, 0.2)",
        },
        bar: {
          borderRadius: 10,
          background: "linear-gradient(90deg, #616161 0%, #8e8e8e 100%)",
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          backdropFilter: "blur(30px) saturate(200%)",
          WebkitBackdropFilter: "blur(30px) saturate(200%)",
          border: "1px solid rgba(255, 255, 255, 0.4)",
          borderTop: "1px solid rgba(255, 255, 255, 0.6)",
          boxShadow: "0 2px 12px 0 rgba(0, 0, 0, 0.1), inset 0 1px 0 0 rgba(255, 255, 255, 0.4)",
        },
      },
    },
  },
});

export function MuiProvider({ children }: { children: ReactNode }) {
  return (
    <AppRouterCacheProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <style jsx global>{`
          body {
            background: linear-gradient(135deg, #e0e0e0 0%, #b0b0b0 50%, #d0d0d0 100%);
            background-attachment: fixed;
            min-height: 100vh;
          }
          * {
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
          }
        `}</style>
        {children}
      </ThemeProvider>
    </AppRouterCacheProvider>
  );
}

