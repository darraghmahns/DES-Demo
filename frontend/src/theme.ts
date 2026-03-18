import { createTheme, type MantineColorsTuple } from '@mantine/core';

const campari: MantineColorsTuple = [
  '#fcedea',
  '#f7d7d0',
  '#efb0a2',
  '#e78872',
  '#df6549',
  '#d95134',
  '#d14429',
  '#c63a2b',
  '#af2f22',
  '#98251a',
];

export const desTheme = createTheme({
  primaryColor: 'campari',
  colors: {
    campari,
    cyan: campari,
  },
  defaultRadius: 'sm',
});
