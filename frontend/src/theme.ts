import { createTheme, type MantineColorsTuple } from '@mantine/core';

const cyan: MantineColorsTuple = [
  '#e8f4ff',
  '#d0e8ff',
  '#a3cfff',
  '#72b5ff',
  '#4d9fff',
  '#3891ff',
  '#2b89ff',
  '#1a76e8',
  '#0969da',
  '#0058c7',
];

export const desTheme = createTheme({
  primaryColor: 'cyan',
  colors: {
    cyan,
  },
  defaultRadius: 'sm',
});
