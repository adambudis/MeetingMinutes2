import { deepPurple, grey, lime } from '@mui/material/colors';
import { createTheme } from '@mui/material/styles';

// Mirrors the WPF BundledTheme: BaseTheme="Light" PrimaryColor="DeepPurple" SecondaryColor="Lime".
export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: deepPurple[500] },
    secondary: { main: lime[500] },
    background: { default: grey[50], paper: '#ffffff' },
  },
  typography: {
    fontFamily: 'Roboto, "Segoe UI", Arial, sans-serif',
    fontSize: 13,
  },
});

/** MaterialDesignToolBarBackground equivalent: assistant bubbles and the input bar. */
export const toolbarBackground = grey[100];
