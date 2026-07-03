export const getInitials = (name?: string) => {
  return name
    ? name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
    : "??";
};
